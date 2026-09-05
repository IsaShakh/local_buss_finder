from dataclasses import replace

import pytest

from apps.campaigns.domain import CampaignValidationError
from apps.campaigns.models import CampaignSourceRun, DiscoveryCampaign
from apps.campaigns.services import start_campaign
from apps.discovery.errors import InvalidSourcePayload
from apps.discovery.services import run_source_discovery_now
from apps.sources.models import SourceRecord, SourceRecordConflict
from apps.taxonomy.models import SourceCategoryMapping


@pytest.mark.django_db(transaction=True)
def test_source_run_streams_payloads_to_storage_and_enqueues_record_ids(
    queued_source_run,
    fixture_adapter,
    fake_store,
    normalization_queue,
):
    run_source_discovery_now(
        source_run_id=queued_source_run.id,
        adapter=fixture_adapter,
        store=fake_store,
        enqueue_normalization=normalization_queue.append,
    )

    queued_source_run.refresh_from_db()
    assert queued_source_run.source_dataset_version == "fixture-2026-09"
    assert queued_source_run.status == CampaignSourceRun.Status.NORMALIZING
    assert queued_source_run.stored_records == 2
    assert SourceRecord.objects.count() == 2
    assert normalization_queue == list(
        SourceRecord.objects.order_by("created_at").values_list("id", flat=True)
    )


@pytest.mark.django_db(transaction=True)
def test_empty_adapter_completes_source_run_with_zero_counters(
    queued_source_run,
    adapter_factory,
    fake_store,
):
    run_source_discovery_now(
        source_run_id=queued_source_run.id,
        adapter=adapter_factory(payloads=()),
        store=fake_store,
        enqueue_normalization=lambda _: pytest.fail("nothing may be enqueued"),
    )

    queued_source_run.refresh_from_db()
    assert queued_source_run.status == CampaignSourceRun.Status.COMPLETED
    assert (
        queued_source_run.discovered_records,
        queued_source_run.stored_records,
        queued_source_run.normalized_records,
        queued_source_run.rejected_records,
        queued_source_run.failed_records,
    ) == (0, 0, 0, 0, 0)


@pytest.mark.django_db(transaction=True)
def test_start_rechecks_mapping_drift_before_enqueue(owner, single_source_draft_campaign):
    SourceCategoryMapping.objects.filter(
        source__campaign_selections__campaign=single_source_draft_campaign
    ).update(is_active=False)
    queued: list[str] = []

    with pytest.raises(CampaignValidationError) as error:
        start_campaign(
            campaign_id=single_source_draft_campaign.id,
            actor=owner,
            enqueue=lambda campaign_id: queued.append(str(campaign_id)),
        )

    single_source_draft_campaign.refresh_from_db()
    assert error.value.code == "SOURCE_HAS_NO_ACTIVE_MAPPINGS"
    assert single_source_draft_campaign.status == DiscoveryCampaign.Status.DRAFT
    assert queued == []


@pytest.mark.django_db(transaction=True)
def test_conflicting_payload_is_counted_once_and_does_not_stop_stream(
    queued_source_run,
    payload,
    parsed,
    adapter_factory,
    fake_store,
    normalization_queue,
):
    changed = replace(payload, payload={**payload.payload, "name": "Changed"})
    run_source_discovery_now(
        source_run_id=queued_source_run.id,
        adapter=adapter_factory(payloads=(payload, changed), parsed=parsed),
        store=fake_store,
        enqueue_normalization=normalization_queue.append,
    )

    queued_source_run.refresh_from_db()
    assert SourceRecord.objects.filter(source_run=queued_source_run).count() == 1
    assert SourceRecordConflict.objects.filter(source_run=queued_source_run).count() == 1
    assert (
        queued_source_run.discovered_records,
        queued_source_run.stored_records,
        queued_source_run.failed_records,
    ) == (2, 2, 1)
    assert len(normalization_queue) == 1


@pytest.mark.django_db(transaction=True)
def test_outside_aoi_is_rejected_once_and_not_enqueued(
    queued_source_run,
    payload,
    parsed,
    adapter_factory,
    fake_store,
    normalization_queue,
):
    outside = replace(parsed, longitude=29.0, latitude=41.0)
    adapter = adapter_factory(payloads=(payload,), parsed=outside)

    run_source_discovery_now(
        source_run_id=queued_source_run.id,
        adapter=adapter,
        store=fake_store,
        enqueue_normalization=normalization_queue.append,
    )

    record = SourceRecord.objects.get()
    queued_source_run.refresh_from_db()
    assert record.normalization_status == SourceRecord.NormalizationStatus.REJECTED
    assert record.normalization_error_code == "OUTSIDE_SEARCH_AREA"
    assert queued_source_run.rejected_records == 1
    assert queued_source_run.status == CampaignSourceRun.Status.COMPLETED
    assert normalization_queue == []


@pytest.mark.django_db(transaction=True)
def test_retry_reuses_persisted_dataset_version(
    running_source_run,
    adapter_factory,
    fake_store,
):
    running_source_run.source_dataset_version = "persisted-release"
    running_source_run.save(update_fields=("source_dataset_version",))
    adapter = adapter_factory(payloads=())

    run_source_discovery_now(
        source_run_id=running_source_run.id,
        adapter=adapter,
        store=fake_store,
        enqueue_normalization=lambda _: None,
    )

    assert adapter.resolve_calls == 0
    assert adapter.requests[0].dataset_version == "persisted-release"


@pytest.mark.django_db(transaction=True)
def test_parser_failure_is_durable_and_finishes_with_errors(
    queued_source_run,
    payload,
    adapter_factory,
    fake_store,
    normalization_queue,
):
    def reject_payload(_):
        raise InvalidSourcePayload("fixture rejected")

    run_source_discovery_now(
        source_run_id=queued_source_run.id,
        adapter=adapter_factory(payloads=(payload,), parsed=reject_payload),
        store=fake_store,
        enqueue_normalization=normalization_queue.append,
    )

    record = SourceRecord.objects.get()
    queued_source_run.refresh_from_db()
    assert record.normalization_status == SourceRecord.NormalizationStatus.FAILED
    assert record.parser_error_code == "INVALID_SOURCE_PAYLOAD"
    assert queued_source_run.failed_records == 1
    assert queued_source_run.status == CampaignSourceRun.Status.COMPLETED_WITH_ERRORS
    assert normalization_queue == []
