import json
from collections.abc import Callable
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.campaigns.models import CampaignSource, CampaignSourceRun, DiscoveryCampaign
from apps.campaigns.progress import finalize_source_run
from apps.discovery.domain import BoundingBox, DiscoveryAdapter, DiscoveryRequest
from apps.discovery.errors import PermanentSourceError
from apps.geography.models import SearchArea
from apps.sources.domain import SourceRecordConflictError
from apps.sources.models import SourceRecord
from apps.sources.services import persist_source_payload
from apps.sources.storage import RawPayloadStore
from apps.taxonomy.services import resolve_external_categories
from common.observability import structured_event


def build_discovery_request(source_run: CampaignSourceRun) -> DiscoveryRequest:
    campaign = source_run.campaign
    search_area = campaign.search_area
    west, south, east, north = search_area.geometry.extent
    category_ids = tuple(campaign.categories.values_list("id", flat=True))
    external_categories = resolve_external_categories(source_run.source_id, category_ids)
    if not external_categories:
        raise PermanentSourceError(
            "SOURCE_HAS_NO_ACTIVE_MAPPINGS",
            f"No active mappings for source {source_run.source.code}",
        )
    selection = CampaignSource.objects.get(
        campaign_id=campaign.id,
        source_id=source_run.source_id,
        is_enabled=True,
    )
    return DiscoveryRequest(
        campaign_id=campaign.id,
        source_run_id=source_run.id,
        search_area_id=search_area.id,
        dataset_version=source_run.source_dataset_version or "",
        bbox=BoundingBox(west=west, south=south, east=east, north=north),
        geometry_geojson=json.loads(search_area.geometry.geojson),
        external_categories=external_categories,
        result_limit=selection.request_limit,
        correlation_id=str(campaign.id),
    )


def reject_source_record_once(*, source_record_id: UUID, error_code: str) -> bool:
    with transaction.atomic():
        references = SourceRecord.objects.values("campaign_id", "source_run_id").get(
            id=source_record_id
        )
        campaign = DiscoveryCampaign.objects.select_for_update().get(id=references["campaign_id"])
        source_run = CampaignSourceRun.objects.select_for_update().get(
            id=references["source_run_id"]
        )
        source_record = SourceRecord.objects.select_for_update().get(id=source_record_id)
        if source_record.normalization_status != SourceRecord.NormalizationStatus.PENDING:
            return False
        source_record.normalization_status = SourceRecord.NormalizationStatus.REJECTED
        source_record.normalization_error_code = error_code
        source_record.save(
            update_fields=("normalization_status", "normalization_error_code", "updated_at")
        )
        source_run.rejected_records += 1
        source_run.save(update_fields=("rejected_records", "updated_at"))
        campaign.rejected_records += 1
        campaign.save(update_fields=("rejected_records", "updated_at"))
        return True


def _coordinates_are_valid(record: SourceRecord) -> bool:
    return record.raw_location is not None and (
        -180 <= record.raw_location.x <= 180 and -90 <= record.raw_location.y <= 90
    )


def _outside_search_area(record: SourceRecord) -> bool:
    if not _coordinates_are_valid(record):
        return False
    return not SearchArea.objects.filter(
        id=record.campaign.search_area_id,
        geometry__covers=record.raw_location,
    ).exists()


def _start_source_run(source_run_id: UUID, adapter: DiscoveryAdapter) -> CampaignSourceRun | None:
    with transaction.atomic():
        campaign_id = CampaignSourceRun.objects.values_list("campaign_id", flat=True).get(
            id=source_run_id
        )
        DiscoveryCampaign.objects.select_for_update().get(id=campaign_id)
        source_run = CampaignSourceRun.objects.select_for_update().get(id=source_run_id)
        if source_run.status in {
            CampaignSourceRun.Status.COMPLETED,
            CampaignSourceRun.Status.COMPLETED_WITH_ERRORS,
            CampaignSourceRun.Status.FAILED,
        }:
            return None
        if source_run.discovery_finished_at is not None:
            return None
        if not source_run.source_dataset_version:
            dataset_version = adapter.resolve_dataset_version().strip()
            if not dataset_version:
                raise PermanentSourceError(
                    "SOURCE_DATASET_VERSION_MISSING",
                    "Adapter returned an empty dataset version",
                )
            source_run.source_dataset_version = dataset_version
        if source_run.status == CampaignSourceRun.Status.PENDING:
            source_run.status = CampaignSourceRun.Status.RUNNING
            source_run.started_at = timezone.now()
        source_run.save(
            update_fields=(
                "status",
                "started_at",
                "source_dataset_version",
                "updated_at",
            )
        )
        transaction.on_commit(
            lambda: structured_event(
                "source_run.started",
                campaign_id=source_run.campaign_id,
                source_run_id=source_run.id,
                source=source_run.source.code,
                correlation_id=str(source_run.campaign_id),
                message="Source run started",
            )
        )
        return source_run


def _finish_discovery(source_run_id: UUID) -> CampaignSourceRun:
    with transaction.atomic():
        campaign_id = CampaignSourceRun.objects.values_list("campaign_id", flat=True).get(
            id=source_run_id
        )
        DiscoveryCampaign.objects.select_for_update().get(id=campaign_id)
        source_run = CampaignSourceRun.objects.select_for_update().get(id=source_run_id)
        if source_run.discovery_finished_at is None:
            source_run.discovery_finished_at = timezone.now()
        if source_run.status not in {
            CampaignSourceRun.Status.COMPLETED,
            CampaignSourceRun.Status.COMPLETED_WITH_ERRORS,
            CampaignSourceRun.Status.FAILED,
        }:
            source_run.status = CampaignSourceRun.Status.NORMALIZING
        source_run.save(update_fields=("discovery_finished_at", "status", "updated_at"))
        transaction.on_commit(
            lambda: structured_event(
                "source_run.discovery_finished",
                campaign_id=source_run.campaign_id,
                source_run_id=source_run.id,
                source=source_run.source.code,
                correlation_id=str(source_run.campaign_id),
                message="Source discovery finished",
            )
        )
        return source_run


def _finalize_ready_run(source_run: CampaignSourceRun) -> None:
    processed = (
        source_run.normalized_records + source_run.rejected_records + source_run.failed_records
    )
    if source_run.discovery_finished_at is None or processed != source_run.stored_records:
        return
    status = (
        CampaignSourceRun.Status.COMPLETED_WITH_ERRORS
        if source_run.failed_records or source_run.error_code
        else CampaignSourceRun.Status.COMPLETED
    )
    finalize_source_run(source_run_id=source_run.id, status=status)


def run_source_discovery_now(
    *,
    source_run_id: UUID,
    adapter: DiscoveryAdapter,
    store: RawPayloadStore,
    enqueue_normalization: Callable[[UUID], None],
) -> None:
    source_run = _start_source_run(source_run_id, adapter)
    if source_run is None:
        return
    request = build_discovery_request(source_run)
    for payload in adapter.discover(request):
        try:
            persisted = persist_source_payload(
                source_run=source_run,
                source_payload=payload,
                parse_payload=adapter.parse_payload,
                store=store,
            )
        except SourceRecordConflictError:
            continue
        if not persisted.created or persisted.normalization_status != "pending":
            continue
        record = SourceRecord.objects.select_related("campaign__search_area").get(
            id=persisted.source_record_id
        )
        if _outside_search_area(record):
            reject_source_record_once(
                source_record_id=record.id,
                error_code="OUTSIDE_SEARCH_AREA",
            )
            continue
        enqueue_normalization(record.id)

    source_run = _finish_discovery(source_run.id)
    _finalize_ready_run(source_run)


def mark_source_discovery_exhausted(
    *,
    source_run_id: UUID,
    error_code: str,
    error_detail: str = "",
) -> CampaignSourceRun.Status:
    with transaction.atomic():
        campaign_id = CampaignSourceRun.objects.values_list("campaign_id", flat=True).get(
            id=source_run_id
        )
        DiscoveryCampaign.objects.select_for_update().get(id=campaign_id)
        source_run = CampaignSourceRun.objects.select_for_update().get(id=source_run_id)
        if source_run.status in {
            CampaignSourceRun.Status.COMPLETED,
            CampaignSourceRun.Status.COMPLETED_WITH_ERRORS,
            CampaignSourceRun.Status.FAILED,
        }:
            return source_run.status
        source_run.discovery_finished_at = source_run.discovery_finished_at or timezone.now()
        source_run.error_code = error_code[:64]
        source_run.error_detail = error_detail[:2000]
        processed = (
            source_run.normalized_records + source_run.rejected_records + source_run.failed_records
        )
        ready = processed == source_run.stored_records
        if not ready:
            source_run.status = CampaignSourceRun.Status.NORMALIZING
        source_run.save(
            update_fields=(
                "discovery_finished_at",
                "error_code",
                "error_detail",
                "status",
                "updated_at",
            )
        )
        transaction.on_commit(
            lambda: structured_event(
                "source_run.discovery_exhausted",
                campaign_id=source_run.campaign_id,
                source_run_id=source_run.id,
                source=source_run.source.code,
                correlation_id=str(source_run.campaign_id),
                error_code=source_run.error_code,
                message="Source discovery exhausted",
            )
        )
    if not ready:
        return CampaignSourceRun.Status.NORMALIZING
    requested_status = (
        CampaignSourceRun.Status.FAILED
        if source_run.stored_records == 0
        else CampaignSourceRun.Status.COMPLETED_WITH_ERRORS
    )
    return finalize_source_run(
        source_run_id=source_run.id,
        status=requested_status,
        error_code=error_code[:64],
        error_detail=error_detail[:2000],
    )


def begin_campaign(campaign_id: UUID) -> tuple[UUID, ...]:
    with transaction.atomic():
        campaign = DiscoveryCampaign.objects.select_for_update().get(id=campaign_id)
        if campaign.status != DiscoveryCampaign.Status.QUEUED:
            return ()
        campaign.status = DiscoveryCampaign.Status.RUNNING
        campaign.started_at = campaign.started_at or timezone.now()
        campaign.save(update_fields=("status", "started_at", "updated_at"))
        transaction.on_commit(
            lambda: structured_event(
                "campaign.started",
                campaign_id=campaign.id,
                correlation_id=str(campaign.id),
                message="Campaign started",
            )
        )
        return tuple(
            campaign.source_runs.filter(status=CampaignSourceRun.Status.PENDING).values_list(
                "id", flat=True
            )
        )


def run_campaign_synchronously(
    campaign_id: UUID,
    *,
    get_adapter: Callable[[str], DiscoveryAdapter],
    store: RawPayloadStore,
) -> None:
    from apps.normalization.tasks import normalize_source_record_now

    source_run_ids = begin_campaign(campaign_id)
    normalization_queue: list[UUID] = []
    for source_run_id in source_run_ids:
        source_code = CampaignSourceRun.objects.values_list("source__code", flat=True).get(
            id=source_run_id
        )
        run_source_discovery_now(
            source_run_id=source_run_id,
            adapter=get_adapter(source_code),
            store=store,
            enqueue_normalization=normalization_queue.append,
        )
    for source_record_id in normalization_queue:
        normalize_source_record_now(source_record_id)
