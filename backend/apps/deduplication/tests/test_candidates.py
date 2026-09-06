from uuid import UUID

import pytest
from django.contrib.gis.geos import Point

from apps.businesses.models import Business
from apps.deduplication.materialization import seed_business

pytestmark = pytest.mark.django_db


def find(record):
    from apps.deduplication.candidates import find_candidate_businesses

    return find_candidate_businesses(normalized_record=record)


def test_source_identity_crosses_campaigns_and_deduplicates_memberships(
    owner, normalized_record_factory
):
    """Catches campaign-local identity matching and duplicate joined business rows."""
    from apps.businesses.models import BusinessSourceMembership

    first = normalized_record_factory(source_code="same")
    second = normalized_record_factory(source_code="same")
    incoming = normalized_record_factory(source_code="same", match_name="unrelated")
    for record in (second, incoming):
        record.source_record.external_id = first.source_record.external_id
        record.source_record.save(update_fields=["external_id"])
    business = seed_business(normalized_record=first, owner_id=owner.id)
    BusinessSourceMembership.objects.create(business=business, normalized_record=second)

    matches = find(incoming)

    assert [match.business_id for match in matches] == [business.id]
    assert matches[0].facts.source_identity
    assert matches[0].assessment.score == 100


@pytest.mark.parametrize(
    ("contact", "value", "signal"),
    [
        ("phones", ["+905321234567"], "phone_match"),
        ("websites", ["https://www.clinic.test/contact"], "domain_match"),
    ],
)
def test_exact_contacts_are_found_without_spatial_or_name_match(
    owner, normalized_record_factory, contact, value, signal
):
    """Catches exact contact branches accidentally depending on location/name gates."""
    first = normalized_record_factory(source_code="first", **{contact: value})
    business = seed_business(normalized_record=first, owner_id=owner.id)
    incoming = normalized_record_factory(
        source_code="second", match_name="unrelated", location=Point(30, 35), **{contact: value}
    )

    matches = find(incoming)

    assert [match.business_id for match in matches] == [business.id]
    assert getattr(matches[0].facts, signal)
    assert not matches[0].assessment.automatic


def test_spatial_requires_name_and_500_metre_distance(owner, normalized_record_factory):
    """Catches degrees-as-metres errors and missing spatial/name qualification."""
    incoming = normalized_record_factory(source_code="incoming", address_text="")
    near = Business.objects.create(
        owner=owner, match_name="alanya smile", location=Point(32.5, 36.504)
    )
    Business.objects.create(owner=owner, match_name="unrelated", location=incoming.location)
    Business.objects.create(owner=owner, match_name="alanya smile", location=Point(32.5, 36.506))
    Business.objects.create(owner=owner, match_name="alanya smile")

    matches = find(incoming)

    assert [match.business_id for match in matches] == [near.id]
    assert 440 < matches[0].facts.distance_m < 450
    assert not matches[0].facts.exact_address


def test_spatial_cap_keeps_best_50_and_all_exact_candidates(
    owner, normalized_record_factory, django_assert_max_num_queries
):
    """Catches a global LIMIT dropping exact matches or per-business fact queries."""
    incoming = normalized_record_factory(source_code="incoming", phones=["+905321234567"])
    businesses = [
        Business(
            id=UUID(int=index), owner=owner, match_name="alanya smile", location=incoming.location
        )
        for index in range(1, 53)
    ]
    Business.objects.bulk_create(businesses)
    exact = Business.objects.create(
        owner=owner, phones=incoming.phones, location=Point(30, 35), match_name="unrelated"
    )

    with django_assert_max_num_queries(8):
        matches = find(incoming)

    assert {match.business_id for match in matches} == {
        *(business.id for business in businesses[:50]),
        exact.id,
    }


@pytest.mark.parametrize("branch", ["source", "phone", "domain", "spatial"])
def test_every_branch_excludes_other_owners_and_merged_rows(
    owner, other_owner, normalized_record_factory, branch
):
    """Catches ownership or active filtering omitted on any union branch."""
    first = normalized_record_factory(
        source_code="same", phones=["+905321234567"], websites=["https://clinic.test"]
    )
    incoming = normalized_record_factory(
        source_code="same",
        phones=first.phones if branch == "phone" else [],
        websites=first.websites if branch == "domain" else [],
        match_name="alanya smile" if branch == "spatial" else "unrelated",
    )
    if branch == "source":
        incoming.source_record.external_id = first.source_record.external_id
        incoming.source_record.save(update_fields=["external_id"])
    business = seed_business(normalized_record=first, owner_id=owner.id)
    survivor = Business.objects.create(owner=owner)
    business.merged_into = survivor
    business.save(update_fields=["merged_into"])
    assert find(incoming) == []

    business.merged_into = None
    business.owner = other_owner
    business.save(update_fields=["merged_into", "owner"])
    assert find(incoming) == []


def test_social_hosts_and_empty_identity_details_do_not_create_exact_matches(
    owner, normalized_record_factory
):
    """Catches treating excluded website hosts or empty fields as shared identity."""
    incoming = normalized_record_factory(
        source_code="incoming",
        websites=["https://instagram.com/clinic"],
        match_name="",
        address_text="",
    )
    Business.objects.create(
        owner=owner,
        domains=["instagram.com"],
        location=incoming.location,
        websites=incoming.websites,
    )
    assert find(incoming) == []


def test_exact_contact_with_missing_incoming_location_is_reviewable(
    owner, normalized_record_factory
):
    """Catches null-distance query failures and automatic attachment without coordinates."""
    incoming = normalized_record_factory(source_code="incoming", phones=["+905321234567"])
    incoming.location = None
    incoming.save(update_fields=["location"])
    business = Business.objects.create(
        owner=owner,
        phones=incoming.phones,
        match_name=incoming.match_name,
        address_text=incoming.address_text,
        location=Point(32.5, 36.5),
    )

    matches = find(incoming)

    assert [match.business_id for match in matches] == [business.id]
    assert matches[0].facts.distance_m is None
    assert matches[0].assessment.score == 85
    assert not matches[0].assessment.automatic


def test_spatial_cap_prefers_similarity_then_distance_before_uuid(owner, normalized_record_factory):
    """Catches capping by distance alone or UUID before the spatial ranking fields."""
    incoming = normalized_record_factory(source_code="incoming")
    Business.objects.bulk_create(
        [
            Business(
                id=UUID(int=index),
                owner=owner,
                match_name="alanya smile",
                location=incoming.location,
            )
            for index in range(100, 149)
        ]
    )
    farther = Business.objects.create(
        id=UUID(int=1), owner=owner, match_name="alanya smile", location=Point(32.5, 36.503)
    )
    nearer = Business.objects.create(
        id=UUID(int=2), owner=owner, match_name="alanya smile", location=Point(32.5, 36.501)
    )
    less_similar = Business.objects.create(
        owner=owner, match_name="alanya smiles", location=incoming.location
    )

    ids = {match.business_id for match in find(incoming)}

    assert len(ids) == 50
    assert nearer.id in ids
    assert farther.id not in ids
    assert less_similar.id not in ids


@pytest.mark.parametrize(
    ("incoming_point", "candidate_point"),
    [(Point(179.999, 36.5), Point(-179.999, 36.5)), (Point(0, 89.999), Point(90, 89.999))],
)
def test_spatial_envelope_handles_antimeridian_and_poles(
    owner, normalized_record_factory, incoming_point, candidate_point
):
    """Catches bounding boxes dropping geodesic neighbours across longitude discontinuities."""
    incoming = normalized_record_factory(source_code="incoming", location=incoming_point)
    business = Business.objects.create(
        owner=owner, match_name=incoming.match_name, location=candidate_point
    )
    assert [match.business_id for match in find(incoming)] == [business.id]
