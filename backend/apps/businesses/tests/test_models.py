from uuid import UUID

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.businesses.models import Business, BusinessSourceMembership, DuplicateCandidate


def create_business(owner):
    return Business.objects.create(owner=owner)


def ordered_businesses(owner):
    first = create_business(owner)
    second = create_business(owner)
    left_id, right_id = DuplicateCandidate.ordered_pair(first.id, second.id)
    businesses = {first.id: first, second.id: second}
    return businesses[left_id], businesses[right_id]


@pytest.mark.django_db
def test_canonical_models_initialize_safe_default_states(owner, records):
    business = create_business(owner)
    membership = BusinessSourceMembership.objects.create(
        business=business,
        normalized_record=records.target.normalized_record,
    )
    left_business, right_business = ordered_businesses(owner)
    candidate = DuplicateCandidate.objects.create(
        owner=owner,
        left_business=left_business,
        right_business=right_business,
    )

    assert business.primary_normalized_record is None
    assert business.display_name == ""
    assert business.normalized_name == ""
    assert business.match_name == ""
    assert business.category is None
    assert business.address_text == ""
    assert business.country is None
    assert business.province is None
    assert business.district is None
    assert business.neighborhood is None
    assert business.location is None
    assert business.phones == []
    assert business.emails == []
    assert business.websites == []
    assert business.domains == []
    assert business.social_urls == {}
    assert business.first_seen_at is None
    assert business.last_seen_at is None
    assert business.resolution_version == "deterministic-v1"
    assert business.merged_into is None
    assert membership.match_kind == BusinessSourceMembership.MatchKind.SEED
    assert membership.match_score == 0
    assert membership.match_signals == []
    assert membership.resolution_version == "deterministic-v1"
    assert membership.attached_at is not None
    assert candidate.score == 0
    assert candidate.signals == []
    assert candidate.resolution_version == "deterministic-v1"
    assert candidate.status == DuplicateCandidate.Status.PENDING
    assert candidate.decided_by is None
    assert candidate.decided_at is None
    assert candidate.survivor_business is None
    assert candidate.merged_business is None
    assert candidate.moved_membership_ids == []


@pytest.mark.django_db
def test_active_businesses_exclude_merged_rows(owner):
    survivor = create_business(owner)
    merged = create_business(owner)
    merged.merged_into = survivor
    merged.full_clean()
    merged.save(update_fields=("merged_into", "updated_at"))

    assert list(Business.active.order_by("id")) == [survivor]


@pytest.mark.django_db
def test_normalized_record_can_have_only_one_membership(owner, records):
    BusinessSourceMembership.objects.create(
        business=create_business(owner),
        normalized_record=records.target.normalized_record,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        BusinessSourceMembership.objects.create(
            business=create_business(owner),
            normalized_record=records.target.normalized_record,
        )


@pytest.mark.django_db
@pytest.mark.parametrize("score", (-1, 101))
def test_membership_rejects_scores_outside_zero_to_one_hundred(owner, records, score):
    membership = BusinessSourceMembership(
        business=create_business(owner),
        normalized_record=records.target.normalized_record,
        match_score=score,
    )

    with pytest.raises(ValidationError):
        membership.full_clean()


@pytest.mark.django_db
@pytest.mark.parametrize("score", (-1, 101))
def test_candidate_rejects_scores_outside_zero_to_one_hundred(owner, score):
    left_business, right_business = ordered_businesses(owner)
    candidate = DuplicateCandidate(
        owner=owner,
        left_business=left_business,
        right_business=right_business,
        score=score,
    )

    with pytest.raises(ValidationError):
        candidate.full_clean()


@pytest.mark.django_db
def test_duplicate_candidate_pair_is_unique_when_written_in_canonical_order(owner):
    left_business, right_business = ordered_businesses(owner)
    DuplicateCandidate.objects.create(
        owner=owner,
        left_business=left_business,
        right_business=right_business,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        DuplicateCandidate.objects.create(
            owner=owner,
            left_business=left_business,
            right_business=right_business,
        )


@pytest.mark.django_db
def test_duplicate_candidate_database_rejects_a_self_pair(owner):
    business = create_business(owner)

    with pytest.raises(IntegrityError), transaction.atomic():
        DuplicateCandidate.objects.create(
            owner=owner,
            left_business=business,
            right_business=business,
        )


@pytest.mark.django_db
def test_business_rejects_a_self_merge(owner):
    business = create_business(owner)
    business.merged_into = business

    with pytest.raises(ValidationError, match="own merged target"):
        business.full_clean()


@pytest.mark.django_db
def test_business_rejects_a_cross_owner_merge(owner, other_owner):
    foreign_business = create_business(other_owner)
    business = create_business(owner)
    business.merged_into = foreign_business

    with pytest.raises(ValidationError, match="same owner"):
        business.full_clean()


@pytest.mark.django_db
def test_candidate_rejects_cross_owner_pair(owner, other_owner):
    left_business = create_business(owner)
    right_business = create_business(other_owner)
    candidate = DuplicateCandidate(
        owner=owner,
        left_business=left_business,
        right_business=right_business,
    )

    with pytest.raises(ValidationError, match="same owner"):
        candidate.full_clean()


@pytest.mark.django_db
def test_candidate_rejects_cross_owner_decision_actor(owner, other_owner):
    left_business, right_business = ordered_businesses(owner)
    candidate = DuplicateCandidate(
        owner=owner,
        left_business=left_business,
        right_business=right_business,
        decided_by=other_owner,
    )

    with pytest.raises(ValidationError, match="decision actor"):
        candidate.full_clean()


def test_ordered_pair_uses_lexical_uuid_order():
    lower = UUID("00000000-0000-0000-0000-000000000001")
    higher = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")

    assert DuplicateCandidate.ordered_pair(higher, lower) == (lower, higher)
