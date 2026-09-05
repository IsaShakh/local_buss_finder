from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from django.db import close_old_connections

from apps.discovery.errors import InvalidSourcePayload
from apps.sources.domain import SourceRecordConflictError
from apps.sources.models import SourceRecord, SourceRecordConflict
from apps.sources.services import persist_source_payload


@pytest.mark.django_db
def test_same_campaign_source_external_id_and_checksum_is_idempotent(
    source_run, payload, parsed, store
):

    first = persist_source_payload(
        source_run=source_run,
        source_payload=payload,
        parse_payload=lambda _: parsed,
        store=store,
    )
    second = persist_source_payload(
        source_run=source_run,
        source_payload=payload,
        parse_payload=lambda _: parsed,
        store=store,
    )

    record = SourceRecord.objects.get()
    source_run.refresh_from_db()
    source_run.campaign.refresh_from_db()
    assert first.created is True
    assert second.created is False
    assert first.source_record_id == second.source_record_id == record.id
    assert first.checksum == second.checksum == record.raw_payload_sha256 == record.checksum
    assert first.raw_payload_key == second.raw_payload_key == record.raw_payload_key
    assert first.normalization_status == second.normalization_status == "pending"
    assert record.source_dataset_version == "fixture-2026-09"
    assert record.source_url == "https://www.openstreetmap.org/node/42"
    assert record.attribution == "© OpenStreetMap contributors"
    assert record.license_code == "ODbL-1.0"
    assert record.raw_name == "Alanya Diş"
    assert record.raw_category == "dentist"
    assert record.raw_address == "Saray, Alanya"
    assert record.raw_phones == ["+90 242 555 0101"]
    assert record.raw_emails == ["info@example.test"]
    assert record.raw_websites == ["https://example.test"]
    assert record.raw_social_urls == {"instagram": ["https://instagram.com/example"]}
    assert record.raw_location.x == 32.0
    assert record.raw_location.y == 36.55
    assert record.raw_payload_bytes > 0
    assert record.payload_schema_version == "1"
    assert record.normalization_retry_count == 0
    assert record.fetched_at == payload.fetched_at
    assert SourceRecord.objects.count() == 1
    assert store.object_count == 1
    assert source_run.discovered_records == 1
    assert source_run.stored_records == 1
    assert source_run.failed_records == 0
    assert source_run.campaign.raw_records_found == 1


@pytest.mark.django_db
def test_changed_payload_creates_one_durable_conflict_and_preserves_first_record(
    source_run, payload, parsed, store
):
    persist_source_payload(
        source_run=source_run,
        source_payload=payload,
        parse_payload=lambda _: parsed,
        store=store,
    )
    changed = replace(payload, payload={**payload.payload, "name": "Changed"})

    for _ in range(2):
        with pytest.raises(SourceRecordConflictError):
            persist_source_payload(
                source_run=source_run,
                source_payload=changed,
                parse_payload=lambda _: replace(parsed, raw_name="Changed"),
                store=store,
            )

    original = SourceRecord.objects.get()
    conflict = SourceRecordConflict.objects.get()
    source_run.refresh_from_db()
    source_run.campaign.refresh_from_db()
    assert original.raw_name == "Alanya Diş"
    assert conflict.original_source_record == original
    assert conflict.external_id == "node/42"
    assert conflict.conflicting_payload_sha256 != original.checksum
    assert conflict.raw_payload_key != original.raw_payload_key
    assert conflict.raw_payload_bytes > 0
    assert conflict.payload_schema_version == "1"
    assert conflict.source_dataset_version == "fixture-2026-09"
    assert conflict.error_code == "SOURCE_RECORD_CONFLICT"
    assert conflict.counted_at is not None
    assert SourceRecordConflict.objects.count() == 1
    assert store.object_count == 2
    assert source_run.discovered_records == 2
    assert source_run.stored_records == 2
    assert source_run.failed_records == 1
    assert source_run.campaign.raw_records_found == 2


@pytest.mark.django_db(transaction=True)
def test_raw_object_is_stored_before_parser_failure_and_failed_counter_is_once_only(
    source_run, payload, store
):
    def failing_parser(_):
        assert store.object_count == 1
        raise InvalidSourcePayload("fixture parser rejected payload")

    first = persist_source_payload(
        source_run=source_run,
        source_payload=payload,
        parse_payload=failing_parser,
        store=store,
    )
    second = persist_source_payload(
        source_run=source_run,
        source_payload=payload,
        parse_payload=failing_parser,
        store=store,
    )

    record = SourceRecord.objects.get(id=first.source_record_id)
    source_run.refresh_from_db()
    assert first.created is True
    assert second.created is False
    assert record.raw_payload_key
    assert record.raw_payload_bytes > 0
    assert record.raw_name is None
    assert record.raw_phones == []
    assert record.normalization_status == "failed"
    assert record.parser_error_code == "INVALID_SOURCE_PAYLOAD"
    assert record.normalization_error_code == "INVALID_SOURCE_PAYLOAD"
    assert source_run.discovered_records == 1
    assert source_run.stored_records == 1
    assert source_run.failed_records == 1


@pytest.mark.django_db
def test_mismatched_parsed_external_id_becomes_failed_source_record(
    source_run, payload, parsed, store
):
    parsed = replace(parsed, external_id="node/other")

    result = persist_source_payload(
        source_run=source_run,
        source_payload=payload,
        parse_payload=lambda _: parsed,
        store=store,
    )

    record = SourceRecord.objects.get(id=result.source_record_id)
    assert result.normalization_status == "failed"
    assert record.parser_error_code == "INVALID_SOURCE_PAYLOAD"
    assert record.raw_name is None


@pytest.mark.django_db
def test_unexpected_parser_crash_can_retry_the_same_raw_object(source_run, payload, parsed, store):
    def crashing_parser(_):
        raise RuntimeError("parser crashed")

    with pytest.raises(RuntimeError, match="parser crashed"):
        persist_source_payload(
            source_run=source_run,
            source_payload=payload,
            parse_payload=crashing_parser,
            store=store,
        )

    source_run.refresh_from_db()
    assert store.object_count == 1
    assert SourceRecord.objects.count() == 0
    assert source_run.stored_records == 0

    retried = persist_source_payload(
        source_run=source_run,
        source_payload=payload,
        parse_payload=lambda _: parsed,
        store=store,
    )
    assert retried.created is True
    assert store.object_count == 1
    assert SourceRecord.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_same_payload_creates_one_record_and_counters_once(
    source_run, payload, parsed, thread_safe_store
):
    def persist_once():
        close_old_connections()
        try:
            run = source_run.__class__.objects.get(id=source_run.id)
            return persist_source_payload(
                source_run=run,
                source_payload=payload,
                parse_payload=lambda _: parsed,
                store=thread_safe_store,
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: persist_once(), range(2)))

    source_run.refresh_from_db()
    assert sorted(result.created for result in results) == [False, True]
    assert SourceRecord.objects.count() == 1
    assert source_run.discovered_records == 1
    assert source_run.stored_records == 1
    assert source_run.failed_records == 0
    assert thread_safe_store.object_count == 1
