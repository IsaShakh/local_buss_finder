from itertools import count
from uuid import uuid4

import pytest
from django.contrib.gis.geos import Point
from django.db import OperationalError
from django.utils import timezone

from apps.businesses.models import Business, BusinessSourceMembership, DuplicateCandidate
from apps.deduplication.services import resolve_normalized_record
from apps.discovery.domain import RawBusinessRecord
from apps.normalization import services
from apps.normalization.services import materialize_normalization, normalize_business_record
from apps.sources.models import NormalizedSourceRecord, SourceRecord


def test_aggregate_keeps_invalid_optional_values_as_warnings():
    raw = RawBusinessRecord(
        external_id="fixture/aggregate",
        raw_name="  Alanya Smile Diş Kliniği LTD. ŞTİ. ",
        raw_category="dentist",
        raw_address="  Atatürk  Cd.\n 12 ",
        raw_phones=("0532 123 45 67", "bad"),
        raw_emails=(" Test@Example.COM ", "bad"),
        raw_websites=("HTTPS://Example.COM/hizmet?x=1#team", "ftp://bad.test"),
        raw_social_urls={"instagram": ("HTTPS://Instagram.COM/alanya/#bio",)},
        longitude=181,
        latitude=36,
    )

    result = normalize_business_record(raw, category_id=None)

    assert result.status == "normalized"
    assert result.error_code is None
    assert result.data is not None
    assert result.data.display_name == "Alanya Smile Diş Kliniği"
    assert result.data.address_text == "Atatürk Cd. 12"
    assert result.data.location is None
    assert result.data.phones == ("+905321234567",)
    assert result.data.emails == ("test@example.com",)
    assert result.data.websites == ("https://example.com/hizmet?x=1",)
    assert result.data.social_urls == {"instagram": ("https://instagram.com/alanya/",)}
    assert result.data.warnings == (
        "INVALID_PHONE",
        "INVALID_EMAIL",
        "INVALID_URL",
        "INVALID_COORDINATES",
        "UNKNOWN_CATEGORY",
    )


def test_aggregate_rejects_missing_name():
    raw = RawBusinessRecord(
        external_id="fixture/missing-name",
        raw_name=" \n ",
        raw_category=None,
        raw_address=None,
        raw_phones=(),
        raw_emails=(),
        raw_websites=(),
        raw_social_urls={},
        longitude=None,
        latitude=None,
    )

    result = normalize_business_record(raw, category_id=None)

    assert result.status == "rejected"
    assert result.data is None
    assert result.error_code == "MISSING_NAME"


def test_invalid_social_url_warns_without_rejecting_record():
    raw = RawBusinessRecord(
        external_id="fixture/invalid-social",
        raw_name="Alanya Smile",
        raw_category="dentist",
        raw_address=None,
        raw_phones=(),
        raw_emails=(),
        raw_websites=(),
        raw_social_urls={"instagram": ("not-a-url",)},
        longitude=32.0,
        latitude=36.55,
    )

    result = normalize_business_record(raw, category_id=uuid4())

    assert result.status == "normalized"
    assert result.data is not None
    assert result.data.social_urls == {"instagram": ()}
    assert result.data.warnings == ("INVALID_URL",)


@pytest.fixture
def source_record_factory(source_run):
    sequence = count(1)

    def create_record(*, longitude=32.0, latitude=36.55, **overrides):
        number = next(sequence)
        location = None
        if longitude is not None and latitude is not None:
            location = Point(longitude, latitude, srid=4326)
        values = {
            "campaign": source_run.campaign,
            "source_run": source_run,
            "source": source_run.source,
            "external_id": f"fixture/{number}",
            "source_dataset_version": "fixture-2026-09",
            "source_url": f"https://example.test/{number}",
            "attribution": "fixture",
            "license_code": "fixture-only",
            "raw_name": "Alanya Smile Diş Kliniği Ltd. Şti.",
            "raw_category": "unknown-category",
            "raw_address": "Saray, Alanya",
            "raw_phones": ["0532 123 45 67"],
            "raw_emails": ["INFO@EXAMPLE.TEST"],
            "raw_websites": ["HTTPS://Example.TEST/path#contact"],
            "raw_social_urls": {"instagram": ["https://instagram.com/example"]},
            "raw_location": location,
            "raw_payload_key": f"raw/fixture/{number}.json.gz",
            "raw_payload_sha256": f"{number:064x}",
            "raw_payload_bytes": 42,
            "payload_schema_version": "1",
            "checksum": f"{number:064x}",
            "fetched_at": timezone.now(),
        }
        values.update(overrides)
        return SourceRecord.objects.create(**values)

    return create_record


@pytest.fixture
def source_record(source_record_factory):
    return source_record_factory()


@pytest.fixture
def source_record_without_name(source_record_factory):
    return source_record_factory(raw_name=None)


@pytest.mark.django_db
def test_unknown_category_is_normalized_with_warning(source_record):
    normalized = materialize_normalization(source_record.id)

    assert normalized is not None
    assert normalized.category_id is None
    assert normalized.warnings == ["UNKNOWN_CATEGORY"]
    assert normalized.normalization_version == "tr-v1"
    assert normalized.location.x == 32.0
    assert normalized.location.y == 36.55
    assert normalized.country_id == source_record.campaign.search_area.country_id
    assert normalized.province_id == source_record.campaign.search_area.province_id
    assert normalized.district_id == source_record.campaign.search_area.district_id
    assert normalized.neighborhood_id == source_record.campaign.search_area.neighborhood_id
    assert normalized.attributes == {"geography_basis": "search_area"}
    source_record.refresh_from_db()
    source_record.source_run.refresh_from_db()
    source_record.campaign.refresh_from_db()
    assert source_record.normalization_status == SourceRecord.NormalizationStatus.NORMALIZED
    assert source_record.source_run.normalized_records == 1
    assert source_record.campaign.normalized_records == 1
    assert Business.active.count() == 1
    membership = BusinessSourceMembership.objects.get()
    assert membership.normalized_record_id == normalized.id
    assert membership.business.owner_id == source_record.campaign.created_by_id


@pytest.mark.django_db
def test_missing_name_rejects_but_preserves_source_record(source_record_without_name):
    normalized = materialize_normalization(source_record_without_name.id)

    assert normalized is None
    source_record_without_name.refresh_from_db()
    source_record_without_name.source_run.refresh_from_db()
    source_record_without_name.campaign.refresh_from_db()
    assert source_record_without_name.normalization_status == "rejected"
    assert source_record_without_name.normalization_error_code == "MISSING_NAME"
    assert source_record_without_name.source_run.rejected_records == 1
    assert source_record_without_name.campaign.rejected_records == 1
    assert NormalizedSourceRecord.objects.count() == 0
    assert not Business.objects.exists()
    assert not BusinessSourceMembership.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("longitude", "latitude", "warning"),
    [(181.0, 36.0, "INVALID_COORDINATES"), (None, None, "MISSING_COORDINATES")],
)
def test_optional_coordinate_problem_keeps_record_normalized(
    source_record_factory, longitude, latitude, warning
):
    record = source_record_factory(longitude=longitude, latitude=latitude)

    normalized = materialize_normalization(record.id)

    assert normalized is not None
    record.refresh_from_db()
    assert record.normalization_status == "normalized"
    assert normalized.location is None
    assert warning in normalized.warnings


@pytest.mark.django_db
def test_repeated_materialization_upserts_one_row_and_counts_once(source_record):
    first = materialize_normalization(source_record.id)
    second = materialize_normalization(source_record.id)

    assert first is not None and second is not None
    assert first.id == second.id
    assert NormalizedSourceRecord.objects.filter(source_record=source_record).count() == 1
    assert Business.active.count() == 1
    assert BusinessSourceMembership.objects.get().normalized_record_id == first.id
    source_record.source_run.refresh_from_db()
    source_record.campaign.refresh_from_db()
    assert source_record.source_run.normalized_records == 1
    assert source_record.campaign.normalized_records == 1


@pytest.mark.django_db
def test_known_category_mapping_is_materialized(source_record_factory, dentist_category):
    record = source_record_factory(raw_category="amenity=dentist")

    normalized = materialize_normalization(record.id)

    assert normalized is not None
    assert normalized.category_id == dentist_category.id
    assert "UNKNOWN_CATEGORY" not in normalized.warnings


@pytest.mark.django_db(transaction=True)
def test_resolver_failure_rolls_back_normalization_and_all_canonical_writes(
    source_record_factory, monkeypatch
):
    """Catches resolution outside the outer transaction or swallowed database failures."""
    baseline = source_record_factory(
        raw_address="", raw_phones=[], raw_emails=[], raw_websites=[], raw_social_urls={}
    )
    baseline_normalized = materialize_normalization(baseline.id)
    resolve_normalized_record(baseline_normalized.id)
    incoming = source_record_factory(
        raw_address="", raw_phones=[], raw_emails=[], raw_websites=[], raw_social_urls={}
    )
    raw_before = list(SourceRecord.objects.order_by("id").values())
    normalized_before = list(NormalizedSourceRecord.objects.values())
    business_before = list(Business.objects.values())
    membership_before = list(BusinessSourceMembership.objects.values())

    def resolve_then_fail(normalized_record_id):
        outcome = resolve_normalized_record(normalized_record_id)
        # Real writes must exist before injecting the database failure: matching
        # name/location with no address/contact scores 55 and creates a review pair.
        assert outcome.action == "seeded"
        assert len(outcome.candidate_ids) == DuplicateCandidate.objects.count() == 1
        assert Business.objects.count() == BusinessSourceMembership.objects.count() == 2
        assert NormalizedSourceRecord.objects.count() == 2
        incoming.source_run.refresh_from_db()
        incoming.campaign.refresh_from_db()
        assert incoming.source_run.normalized_records == incoming.campaign.normalized_records == 2
        raise OperationalError("injected resolution failure")

    monkeypatch.setattr(services, "resolve_normalized_record", resolve_then_fail, raising=False)

    with pytest.raises(OperationalError, match="injected resolution failure"):
        materialize_normalization(incoming.id)

    assert list(SourceRecord.objects.order_by("id").values()) == raw_before
    assert list(NormalizedSourceRecord.objects.values()) == normalized_before
    assert list(Business.objects.values()) == business_before
    assert list(BusinessSourceMembership.objects.values()) == membership_before
    assert not DuplicateCandidate.objects.exists()
    incoming.source_run.refresh_from_db()
    incoming.campaign.refresh_from_db()
    assert incoming.source_run.normalized_records == incoming.campaign.normalized_records == 1
    assert incoming.source_run.rejected_records == incoming.campaign.rejected_records == 0
