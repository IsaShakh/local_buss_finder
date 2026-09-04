from datetime import UTC, datetime

import pytest
from django.contrib.gis.geos import Point
from django.db import IntegrityError, transaction

from apps.sources.models import SourceRecord, SourceRecordConflict

pytestmark = pytest.mark.django_db


def _source_record_values(source_run):
    return {
        "campaign": source_run.campaign,
        "source_run": source_run,
        "source": source_run.source,
        "external_id": "node/42",
        "source_dataset_version": "fixture-2026-09",
        "source_url": "https://www.openstreetmap.org/node/42",
        "attribution": "© OpenStreetMap contributors",
        "license_code": "ODbL-1.0",
        "raw_name": "Alanya Diş",
        "raw_category": "dentist",
        "raw_address": "Saray, Alanya",
        "raw_location": Point(32.0, 36.55, srid=4326),
        "raw_payload_key": "raw/osm/campaign/external/checksum.json.gz",
        "raw_payload_sha256": "a" * 64,
        "raw_payload_bytes": 128,
        "payload_schema_version": "1",
        "checksum": "a" * 64,
        "fetched_at": datetime(2026, 9, 4, 9, 30, tzinfo=UTC),
    }


def test_source_record_has_safe_defaults_and_source_run_relation(source_run):
    record = SourceRecord.objects.create(**_source_record_values(source_run))

    assert source_run.records.get() == record
    assert record.raw_phones == []
    assert record.raw_emails == []
    assert record.raw_websites == []
    assert record.raw_social_urls == {}
    assert record.raw_location.x == 32.0
    assert record.raw_location.y == 36.55
    assert record.normalization_status == "pending"
    assert record.normalization_retry_count == 0
    assert record.normalization_error_code is None
    assert record.parser_error_code is None


def test_source_record_uniqueness_is_guarded_by_database(source_run):
    values = _source_record_values(source_run)
    SourceRecord.objects.create(**values)

    with pytest.raises(IntegrityError), transaction.atomic():
        SourceRecord.objects.create(**{**values, "checksum": "b" * 64})


def test_source_record_conflict_uniqueness_is_guarded_by_database(source_run):
    original = SourceRecord.objects.create(**_source_record_values(source_run))
    values = {
        "campaign": source_run.campaign,
        "source_run": source_run,
        "source": source_run.source,
        "external_id": original.external_id,
        "original_source_record": original,
        "conflicting_payload_sha256": "b" * 64,
        "raw_payload_key": "raw/osm/campaign/external/conflict.json.gz",
        "raw_payload_bytes": 96,
        "payload_schema_version": "1",
        "source_dataset_version": "fixture-2026-09",
    }
    SourceRecordConflict.objects.create(**values)

    with pytest.raises(IntegrityError), transaction.atomic():
        SourceRecordConflict.objects.create(**values)
