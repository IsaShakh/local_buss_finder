from collections.abc import Callable

from django.contrib.gis.geos import Point
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.campaigns.models import CampaignSourceRun, DiscoveryCampaign
from apps.discovery.domain import RawBusinessRecord, SourcePayload
from apps.discovery.errors import InvalidSourcePayload

from .domain import (
    PersistedSourceRecord,
    SourceRecordConflictError,
)
from .models import SourceRecord, SourceRecordConflict
from .storage import RawPayloadStore, StoredPayload

PAYLOAD_SCHEMA_VERSION = "1"


def _parse_source_payload(
    source_payload: SourcePayload,
    parse_payload: Callable[[SourcePayload], RawBusinessRecord],
) -> tuple[RawBusinessRecord | None, str | None]:
    try:
        parsed = parse_payload(source_payload)
        if parsed.external_id != source_payload.external_id:
            raise InvalidSourcePayload("parsed external_id does not match payload")
    except InvalidSourcePayload as error:
        return None, error.code
    return parsed, None


def _raw_location(parsed: RawBusinessRecord | None) -> Point | None:
    if parsed is None or parsed.longitude is None or parsed.latitude is None:
        return None
    return Point(parsed.longitude, parsed.latitude, srid=4326)


def _create_source_record(
    *,
    source_run: CampaignSourceRun,
    source_payload: SourcePayload,
    stored: StoredPayload,
    parsed: RawBusinessRecord | None,
    parser_error_code: str | None,
) -> SourceRecord:
    failed = parser_error_code is not None
    return SourceRecord.objects.create(
        campaign_id=source_run.campaign_id,
        source_run=source_run,
        source_id=source_run.source_id,
        external_id=source_payload.external_id,
        source_dataset_version=source_payload.provenance.dataset_version,
        source_url=source_payload.provenance.source_url,
        attribution=source_payload.provenance.attribution,
        license_code=source_payload.provenance.license_code,
        raw_name=None if parsed is None else parsed.raw_name,
        raw_category=None if parsed is None else parsed.raw_category,
        raw_address=None if parsed is None else parsed.raw_address,
        raw_phones=[] if parsed is None else parsed.raw_phones,
        raw_emails=[] if parsed is None else parsed.raw_emails,
        raw_websites=[] if parsed is None else parsed.raw_websites,
        raw_social_urls={} if parsed is None else parsed.raw_social_urls,
        raw_location=_raw_location(parsed),
        raw_payload_key=stored.key,
        raw_payload_sha256=stored.sha256,
        raw_payload_bytes=stored.size_bytes,
        payload_schema_version=PAYLOAD_SCHEMA_VERSION,
        checksum=stored.sha256,
        normalization_status=(
            SourceRecord.NormalizationStatus.FAILED
            if failed
            else SourceRecord.NormalizationStatus.PENDING
        ),
        normalization_error_code=parser_error_code,
        parser_error_code=parser_error_code,
        fetched_at=source_payload.fetched_at,
    )


def _increment_payload_counters(
    *,
    source_run: CampaignSourceRun,
    campaign: DiscoveryCampaign,
    failed: bool,
) -> None:
    now = timezone.now()
    run_updates = {
        "discovered_records": F("discovered_records") + 1,
        "stored_records": F("stored_records") + 1,
        "updated_at": now,
    }
    if failed:
        run_updates["failed_records"] = F("failed_records") + 1
    CampaignSourceRun.objects.filter(id=source_run.id).update(**run_updates)
    DiscoveryCampaign.objects.filter(id=campaign.id).update(
        raw_records_found=F("raw_records_found") + 1,
        updated_at=now,
    )


def _persist_under_lock(
    *,
    source_run: CampaignSourceRun,
    source_payload: SourcePayload,
    stored: StoredPayload,
    parsed: RawBusinessRecord | None,
    parser_error_code: str | None,
) -> tuple[PersistedSourceRecord | None, bool]:
    campaign = DiscoveryCampaign.objects.select_for_update().get(id=source_run.campaign_id)
    locked_run = (
        CampaignSourceRun.objects.select_for_update().select_related("source").get(id=source_run.id)
    )
    existing = SourceRecord.objects.filter(
        campaign=campaign,
        source=locked_run.source,
        external_id=source_payload.external_id,
    ).first()
    if existing is not None and existing.checksum == stored.sha256:
        return (
            PersistedSourceRecord(
                source_record_id=existing.id,
                created=False,
                raw_payload_key=existing.raw_payload_key,
                checksum=existing.checksum,
                normalization_status=existing.normalization_status,
            ),
            False,
        )

    if existing is not None:
        _, conflict_created = SourceRecordConflict.objects.get_or_create(
            campaign=campaign,
            source_run=locked_run,
            source=locked_run.source,
            external_id=source_payload.external_id,
            conflicting_payload_sha256=stored.sha256,
            defaults={
                "original_source_record": existing,
                "raw_payload_key": stored.key,
                "raw_payload_bytes": stored.size_bytes,
                "payload_schema_version": PAYLOAD_SCHEMA_VERSION,
                "source_dataset_version": source_payload.provenance.dataset_version,
                "counted_at": timezone.now(),
            },
        )
        if conflict_created:
            _increment_payload_counters(
                source_run=locked_run,
                campaign=campaign,
                failed=True,
            )
        return None, True

    record = _create_source_record(
        source_run=locked_run,
        source_payload=source_payload,
        stored=stored,
        parsed=parsed,
        parser_error_code=parser_error_code,
    )
    _increment_payload_counters(
        source_run=locked_run,
        campaign=campaign,
        failed=parser_error_code is not None,
    )
    return (
        PersistedSourceRecord(
            source_record_id=record.id,
            created=True,
            raw_payload_key=record.raw_payload_key,
            checksum=record.checksum,
            normalization_status=record.normalization_status,
        ),
        False,
    )


def persist_source_payload(
    *,
    source_run: CampaignSourceRun,
    source_payload: SourcePayload,
    parse_payload: Callable[[SourcePayload], RawBusinessRecord],
    store: RawPayloadStore,
) -> PersistedSourceRecord:
    stored = store.put_json(
        source_code=source_run.source.code,
        campaign_id=source_run.campaign_id,
        external_id=source_payload.external_id,
        payload=source_payload.payload,
        metadata={
            "payload-schema-version": PAYLOAD_SCHEMA_VERSION,
            "source-dataset-version": source_payload.provenance.dataset_version,
        },
    )
    parsed, parser_error_code = _parse_source_payload(source_payload, parse_payload)

    with transaction.atomic():
        result, conflict_detected = _persist_under_lock(
            source_run=source_run,
            source_payload=source_payload,
            stored=stored,
            parsed=parsed,
            parser_error_code=parser_error_code,
        )

    if conflict_detected:
        raise SourceRecordConflictError
    if result is None:
        raise RuntimeError("source persistence completed without an outcome")
    return result
