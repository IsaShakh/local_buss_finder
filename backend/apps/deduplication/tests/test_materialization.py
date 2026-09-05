from datetime import UTC, datetime
from uuid import UUID

import pytest
from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError

from apps.businesses.models import Business, BusinessSourceMembership
from apps.deduplication.materialization import (
    completeness_score,
    rebuild_business,
    seed_business,
    select_primary_record,
)
from apps.taxonomy.models import BusinessCategory


def test_completeness_score_counts_the_eight_approved_field_groups(normalized_record_factory):
    """Catches adding contact elements instead of the eight canonical completeness groups."""
    category = BusinessCategory.objects.create(name="Clinic", slug="fixture-clinic")
    record = normalized_record_factory(
        source_code="complete",
        category=category,
        phones=["+905321234567"],
        emails=["info@example.test"],
        websites=["https://example.test"],
        social_urls={"instagram": ["https://instagram.com/example"]},
    )

    assert completeness_score(record) == 8


def test_select_primary_record_applies_every_stable_tie_breaker(normalized_record_factory):
    """Catches a primary sort that ignores completeness, recency, source, or normalized UUID."""
    less_complete = normalized_record_factory(
        source_code="first", fetched_at=datetime(2026, 9, 7, tzinfo=UTC), address_text=""
    )
    more_complete = normalized_record_factory(
        source_code="last", fetched_at=datetime(2026, 9, 1, tzinfo=UTC)
    )
    assert select_primary_record((less_complete, more_complete)) == more_complete

    older = normalized_record_factory(
        source_code="first", fetched_at=datetime(2026, 9, 1, tzinfo=UTC)
    )
    newer = normalized_record_factory(
        source_code="last", fetched_at=datetime(2026, 9, 2, tzinfo=UTC)
    )
    assert select_primary_record((older, newer)) == newer

    zeta = normalized_record_factory(
        source_code="zeta", fetched_at=datetime(2026, 9, 3, tzinfo=UTC)
    )
    alpha = normalized_record_factory(
        source_code="alpha", fetched_at=datetime(2026, 9, 3, tzinfo=UTC)
    )
    assert select_primary_record((zeta, alpha)) == alpha

    larger_id = normalized_record_factory(
        source_code="same",
        fetched_at=datetime(2026, 9, 4, tzinfo=UTC),
        normalized_id=UUID("00000000-0000-0000-0000-000000000002"),
    )
    smaller_id = normalized_record_factory(
        source_code="same",
        fetched_at=datetime(2026, 9, 4, tzinfo=UTC),
        normalized_id=UUID("00000000-0000-0000-0000-000000000001"),
    )
    assert select_primary_record((larger_id, smaller_id)) == smaller_id


@pytest.mark.django_db
def test_rebuild_materializes_primary_scalars_and_deterministic_contact_unions(
    owner, normalized_record_factory
):
    """Catches source-order-dependent unions or projecting canonical fields from a non-primary row."""
    category = BusinessCategory.objects.create(name="Primary category", slug="primary-category")
    primary = normalized_record_factory(
        source_code="alpha",
        fetched_at=datetime(2026, 9, 2, tzinfo=UTC),
        display_name="Primary Clinic",
        normalized_name="primary clinic",
        match_name="primary clinic",
        category=category,
        address_text="Primary address",
        location=Point(32.1, 36.1, srid=4326),
        phones=["0532 123 45 67", "+90 532 123 45 67"],
        emails=[" INFO@EXAMPLE.TEST "],
        websites=["HTTPS://WWW.Example.TEST/contact", "https://instagram.com/clinic"],
        social_urls={"instagram": ["http://Instagram.com/clinic"], "facebook": []},
    )
    secondary = normalized_record_factory(
        source_code="beta",
        fetched_at=datetime(2026, 9, 1, tzinfo=UTC),
        display_name="Secondary Clinic",
        normalized_name="secondary clinic",
        match_name="secondary clinic",
        address_text="Secondary address",
        location=Point(31.9, 35.9, srid=4326),
        phones=["+90 242 555 01 01", "0532 123 45 67"],
        emails=["support@example.test", "info@example.test"],
        websites=[
            "https://example.test/about",
            "https://booking.com/property/clinic",
            "https://Directory.Example.test/listing",
        ],
        social_urls={
            "instagram": ["https://instagram.com/clinic", "https://instagram.com/other"],
            "youtube": ["http://youtube.com/clinic"],
        },
    )
    business = seed_business(normalized_record=secondary, owner_id=owner.id)
    assert BusinessSourceMembership.objects.get(normalized_record=secondary).match_kind == (
        BusinessSourceMembership.MatchKind.SEED
    )
    BusinessSourceMembership.objects.create(
        business=business,
        normalized_record=primary,
        match_kind=BusinessSourceMembership.MatchKind.AUTOMATIC,
    )

    rebuilt = rebuild_business(business_id=business.id)

    assert rebuilt.primary_normalized_record_id == primary.id
    assert (rebuilt.display_name, rebuilt.normalized_name, rebuilt.match_name) == (
        "Primary Clinic",
        "primary clinic",
        "primary clinic",
    )
    assert rebuilt.address_text == "Primary address"
    assert rebuilt.category_id == category.id
    assert rebuilt.location == Point(32.1, 36.1, srid=4326)
    assert (
        rebuilt.country_id,
        rebuilt.province_id,
        rebuilt.district_id,
        rebuilt.neighborhood_id,
    ) == (
        primary.country_id,
        primary.province_id,
        primary.district_id,
        primary.neighborhood_id,
    )
    assert rebuilt.phones == ["+902425550101", "+905321234567"]
    assert rebuilt.emails == ["info@example.test", "support@example.test"]
    assert rebuilt.websites == [
        "https://booking.com/property/clinic",
        "https://directory.example.test/listing",
        "https://example.test/about",
        "https://instagram.com/clinic",
        "https://www.example.test/contact",
    ]
    assert rebuilt.domains == ["directory.example.test", "example.test"]
    assert rebuilt.social_urls == {
        "facebook": [],
        "instagram": ["https://instagram.com/clinic", "https://instagram.com/other"],
        "youtube": ["https://youtube.com/clinic"],
    }
    assert rebuilt.first_seen_at == datetime(2026, 9, 1, tzinfo=UTC)
    assert rebuilt.last_seen_at == datetime(2026, 9, 2, tzinfo=UTC)


@pytest.mark.django_db
@pytest.mark.parametrize("additional_memberships", [0, 8])
def test_rebuild_is_byte_stable_with_constant_validation_query_budget(
    owner, normalized_record_factory, django_assert_num_queries, additional_memberships
):
    """Catches unstable JSON/contact ordering or per-membership database queries during rebuilds."""
    first = normalized_record_factory(
        source_code="alpha",
        fetched_at=datetime(2026, 9, 1, tzinfo=UTC),
        phones=["+905321234567"],
        websites=["https://example.test"],
    )
    second = normalized_record_factory(
        source_code="beta",
        fetched_at=datetime(2026, 9, 2, tzinfo=UTC),
        emails=["info@example.test"],
    )
    business = seed_business(normalized_record=first, owner_id=owner.id)
    BusinessSourceMembership.objects.create(business=business, normalized_record=second)
    for _ in range(additional_memberships):
        record = normalized_record_factory(source_code="extra")
        BusinessSourceMembership.objects.create(business=business, normalized_record=record)

    # Two reads + one write, plus six fixed foreign-key checks from full_clean.
    # The budget stays constant with two or ten memberships.
    with django_assert_num_queries(9):
        rebuild_business(business_id=business.id)
    business.refresh_from_db()
    first_snapshot = {
        field: getattr(business, field)
        for field in (
            "primary_normalized_record_id",
            "display_name",
            "normalized_name",
            "match_name",
            "category_id",
            "address_text",
            "country_id",
            "province_id",
            "district_id",
            "neighborhood_id",
            "location",
            "phones",
            "emails",
            "websites",
            "domains",
            "social_urls",
            "first_seen_at",
            "last_seen_at",
            "resolution_version",
        )
    }

    rebuild_business(business_id=business.id)
    business.refresh_from_db()
    assert {field: getattr(business, field) for field in first_snapshot} == first_snapshot


@pytest.mark.django_db
def test_rebuild_rejects_a_merged_business(owner, normalized_record_factory):
    """Catches mutating canonical fields on a business that has been merged into another row."""
    source_record = normalized_record_factory(source_code="source")
    survivor = Business.objects.create(owner=owner)
    merged = seed_business(normalized_record=source_record, owner_id=owner.id)
    Business.objects.filter(id=merged.id).update(merged_into=survivor)

    with pytest.raises(ValueError, match="merged"):
        rebuild_business(business_id=merged.id)


@pytest.mark.django_db
def test_rebuild_validates_canonical_business_before_saving(owner, normalized_record_factory):
    """Catches saving canonical contact changes while the business state is invalid."""
    record = normalized_record_factory(source_code="validation", emails=["new@example.test"])
    business = Business.objects.create(owner=owner, resolution_version="")
    BusinessSourceMembership.objects.create(business=business, normalized_record=record)
    before = Business.objects.values().get(id=business.id)

    with pytest.raises(ValidationError, match="resolution_version"):
        rebuild_business(business_id=business.id)

    assert Business.objects.values().get(id=business.id) == before


@pytest.mark.django_db
def test_seed_business_rejects_a_normalized_record_owned_by_another_user(
    owner, other_owner, normalized_record_factory
):
    """Catches seeding a tenant's business from another tenant's normalized data."""
    normalized_record = normalized_record_factory(source_code="foreign-source")
    business_count = Business.objects.count()
    membership_count = BusinessSourceMembership.objects.count()

    with pytest.raises(ValidationError, match="same owner"):
        seed_business(normalized_record=normalized_record, owner_id=other_owner.id)

    assert Business.objects.count() == business_count
    assert BusinessSourceMembership.objects.count() == membership_count
