import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.businesses.models import Business, BusinessSourceMembership, DuplicateCandidate
from apps.sources.models import NormalizedSourceRecord, SourceRecord

pytestmark = pytest.mark.django_db


def decide(action, candidate, actor):
    from apps.deduplication.decisions import confirm_duplicate, reject_duplicate

    handler = confirm_duplicate if action == "confirmed" else reject_duplicate
    return handler(candidate_id=candidate.id, actor=actor)


def pair(owner, first, second, **kwargs):
    left_id, right_id = sorted((first.id, second.id), key=str)
    return DuplicateCandidate.objects.create(
        owner=owner, left_business_id=left_id, right_business_id=right_id, score=75, **kwargs
    )


@pytest.fixture
def business_factory(owner, normalized_record_factory):
    def create(*, number=1, business_id=None, created_at=None, **record_values):
        business = Business.objects.create(owner=owner, id=business_id or uuid4())
        if created_at is not None:
            Business.objects.filter(id=business.id).update(created_at=created_at)
        for _ in range(number):
            record = normalized_record_factory(source_code="decisions", **record_values)
            BusinessSourceMembership.objects.create(business=business, normalized_record=record)
        return business

    return create


@pytest.mark.parametrize(
    ("first_count", "second_count", "first_day", "second_day", "winner"),
    [(1, 2, 1, 2, 2), (1, 1, 2, 1, 2), (1, 1, 1, 1, 1)],
)
def test_survivor_uses_count_then_oldest_creation_then_smallest_uuid(
    owner, business_factory, first_count, second_count, first_day, second_day, winner
):
    """Catches reversing a ranking key or letting a later key override an earlier one."""
    first = business_factory(
        number=first_count,
        business_id=UUID(int=1),
        created_at=datetime(2026, 9, first_day, tzinfo=UTC),
    )
    second = business_factory(
        number=second_count,
        business_id=UUID(int=2),
        created_at=datetime(2026, 9, second_day, tzinfo=UTC),
    )

    result = decide("confirmed", pair(owner, first, second), owner)

    assert result.survivor_business_id == UUID(int=winner)
    assert result.merged_business_id == UUID(int=3 - winner)


def test_confirm_moves_all_memberships_in_one_update_and_retains_sources_and_loser(
    owner, business_factory
):
    """Catches partial/per-row moves, lost evidence, deleted source rows or canonical rows."""
    survivor = business_factory(number=3)
    loser = business_factory(number=2)
    memberships = list(loser.memberships.order_by("id"))
    # Deliberately make attached order disagree with lexical audit order.
    BusinessSourceMembership.objects.filter(id=memberships[0].id).update(
        attached_at=timezone.now() + timedelta(days=1)
    )
    source_before = list(SourceRecord.objects.order_by("id").values())
    normalized_before = list(NormalizedSourceRecord.objects.order_by("id").values())
    membership_before = list(BusinessSourceMembership.objects.order_by("id").values())
    loser_before = Business.objects.values().get(id=loser.id)
    candidate = pair(owner, survivor, loser)
    started = timezone.now()

    with CaptureQueriesContext(connection) as queries:
        result = decide("confirmed", candidate, owner)

    result.refresh_from_db()
    assert result.status == "confirmed"
    assert result.decided_by_id == owner.id
    assert started <= result.decided_at <= timezone.now()
    assert result.moved_membership_ids == [str(row.id) for row in memberships]
    assert survivor.memberships.count() == 5
    assert loser.memberships.count() == 0
    assert Business.objects.count() == 2
    assert list(Business.active.values_list("id", flat=True)) == [survivor.id]
    loser_after = Business.objects.values().get(id=loser.id)
    assert loser_after.pop("merged_into_id") == survivor.id
    loser_before.pop("merged_into_id")
    loser_before.pop("updated_at")
    loser_after.pop("updated_at")
    assert loser_after == loser_before
    assert list(SourceRecord.objects.order_by("id").values()) == source_before
    assert list(NormalizedSourceRecord.objects.order_by("id").values()) == normalized_before
    for row in membership_before:
        row["business_id"] = survivor.id
    assert list(BusinessSourceMembership.objects.order_by("id").values()) == membership_before
    updates = [
        q["sql"]
        for q in queries
        if q["sql"].startswith('UPDATE "businesses_businesssourcemembership"')
    ]
    assert len(updates) == 1


def test_confirm_rebuilds_every_contact_union(owner, business_factory):
    """Catches merging memberships without rebuilding canonical contact unions."""
    first = business_factory(
        phones=["0532 123 45 67"],
        emails=["FIRST@EXAMPLE.TEST"],
        websites=["https://first.test"],
        social_urls={"instagram": ["https://instagram.com/first"]},
    )
    second = business_factory(
        phones=["+90 242 555 01 01"],
        emails=["second@example.test"],
        websites=["https://second.test"],
        social_urls={"instagram": ["https://instagram.com/second"]},
    )

    result = decide("confirmed", pair(owner, first, second), owner)
    business = Business.objects.get(id=result.survivor_business_id)

    assert business.phones == ["+902425550101", "+905321234567"]
    assert business.emails == ["first@example.test", "second@example.test"]
    assert business.websites == ["https://first.test", "https://second.test"]
    assert business.domains == ["first.test", "second.test"]
    assert business.social_urls == {
        "instagram": ["https://instagram.com/first", "https://instagram.com/second"]
    }
    assert business.primary_normalized_record_id is not None


def test_confirm_supersedes_only_pending_pairs_touching_loser(owner, business_factory):
    """Catches missing either pair side, rewriting decisions, or superseding survivor pairs."""
    loser = business_factory(business_id=UUID(int=3))
    survivor = business_factory(number=2, business_id=UUID(int=5))
    lower = business_factory(business_id=UUID(int=1))
    upper = business_factory(business_id=UUID(int=7))
    terminal = business_factory(business_id=UUID(int=9))
    pending_left = pair(owner, lower, loser)
    pending_right = pair(owner, loser, upper)
    unaffected = pair(owner, survivor, upper)
    rejected = pair(
        owner, loser, terminal, status="rejected", decided_by=owner, decided_at=timezone.now()
    )
    rejected_before = DuplicateCandidate.objects.values().get(id=rejected.id)

    decide("confirmed", pair(owner, survivor, loser), owner)

    assert set(
        DuplicateCandidate.objects.filter(id__in=[pending_left.id, pending_right.id]).values_list(
            "status", flat=True
        )
    ) == {"superseded"}
    unaffected.refresh_from_db()
    assert unaffected.status == "pending"
    assert DuplicateCandidate.objects.values().get(id=rejected.id) == rejected_before


def test_reject_records_actor_and_time_without_business_or_membership_changes(
    owner, business_factory
):
    """Catches reject accidentally merging, rebuilding, or omitting durable decision audit."""
    candidate = pair(owner, business_factory(), business_factory())
    businesses = list(Business.objects.order_by("id").values())
    memberships = list(BusinessSourceMembership.objects.order_by("id").values())
    started = timezone.now()

    result = decide("rejected", candidate, owner)

    result.refresh_from_db()
    assert result.status == "rejected"
    assert result.decided_by_id == owner.id
    assert started <= result.decided_at <= timezone.now()
    assert result.survivor_business_id is result.merged_business_id is None
    assert result.moved_membership_ids == []
    assert list(Business.objects.order_by("id").values()) == businesses
    assert list(BusinessSourceMembership.objects.order_by("id").values()) == memberships


@pytest.mark.parametrize("action", ["confirmed", "rejected"])
@pytest.mark.parametrize("status", ["confirmed", "rejected", "superseded"])
def test_terminal_decisions_cannot_be_repeated_or_changed(owner, business_factory, action, status):
    """Catches overwriting any terminal decision, including switching confirm to reject."""
    from apps.deduplication.exceptions import DuplicateCandidateNotPending

    candidate = pair(owner, business_factory(), business_factory(), status=status)
    before = DuplicateCandidate.objects.values().get(id=candidate.id)
    with pytest.raises(DuplicateCandidateNotPending) as error:
        decide(action, candidate, owner)
    assert error.value.code == "DUPLICATE_CANDIDATE_NOT_PENDING"
    assert DuplicateCandidate.objects.values().get(id=candidate.id) == before
    assert Business.active.count() == 2


@pytest.mark.parametrize("action", ["confirmed", "rejected"])
@pytest.mark.parametrize("merged_side", ["left_business", "right_business"])
def test_stale_pending_pair_with_either_merged_business_is_rejected(
    owner, business_factory, action, merged_side
):
    """Catches checking pending status without detecting a previously merged participant."""
    from apps.deduplication.exceptions import DuplicateCandidateNotPending

    candidate = pair(owner, business_factory(), business_factory())
    target = business_factory()
    Business.objects.filter(id=getattr(candidate, f"{merged_side}_id")).update(merged_into=target)
    with pytest.raises(DuplicateCandidateNotPending):
        decide(action, candidate, owner)
    candidate.refresh_from_db()
    assert candidate.status == "pending"
    assert candidate.decided_at is None


@pytest.mark.parametrize("action", ["confirmed", "rejected"])
def test_foreign_owner_candidate_is_indistinguishable_from_missing(
    owner, other_owner, business_factory, action
):
    """Catches leaking candidate existence or authorizing a different owner's decision."""
    candidate = pair(owner, business_factory(), business_factory())
    for candidate_id in (candidate.id, uuid4()):
        with pytest.raises(DuplicateCandidate.DoesNotExist):
            decide(action, DuplicateCandidate(id=candidate_id), other_owner)
    candidate.refresh_from_db()
    assert candidate.status == "pending"
    assert Business.active.count() == 2


def test_invalid_superseded_pair_rolls_back_the_entire_confirmation(
    owner, business_factory, django_capture_on_commit_callbacks
):
    """Catches skipped full_clean on superseded rows or partial merges on late validation errors."""
    survivor = business_factory(number=2)
    loser = business_factory()
    candidate = pair(owner, survivor, loser)
    pair(owner, loser, business_factory(), resolution_version="")
    businesses = list(Business.objects.order_by("id").values())
    memberships = list(BusinessSourceMembership.objects.order_by("id").values())
    candidates = list(DuplicateCandidate.objects.order_by("id").values())

    with (
        django_capture_on_commit_callbacks(execute=True) as callbacks,
        pytest.raises(ValidationError, match="resolution_version"),
    ):
        decide("confirmed", candidate, owner)

    assert callbacks == []
    assert list(Business.objects.order_by("id").values()) == businesses
    assert list(BusinessSourceMembership.objects.order_by("id").values()) == memberships
    assert list(DuplicateCandidate.objects.order_by("id").values()) == candidates


def test_confirm_rejects_foreign_membership_before_any_move(
    owner,
    other_owner,
    business_factory,
    normalized_record_factory,
    django_capture_on_commit_callbacks,
    caplog,
):
    """Catches materializing foreign contacts from a corrupt losing membership."""
    survivor = business_factory(number=3)
    loser = business_factory()
    foreign_record = normalized_record_factory(
        source_code="foreign", emails=["private@foreign.test"]
    )
    campaign = foreign_record.source_record.campaign
    campaign.created_by = other_owner
    campaign.save(update_fields=["created_by"])
    # bulk_create deliberately bypasses ownership validation, simulating corrupt data.
    BusinessSourceMembership.objects.bulk_create(
        [BusinessSourceMembership(business=loser, normalized_record=foreign_record)]
    )
    candidate = pair(owner, survivor, loser)
    businesses = list(Business.objects.order_by("id").values())
    memberships = list(BusinessSourceMembership.objects.order_by("id").values())
    candidates = list(DuplicateCandidate.objects.order_by("id").values())
    caplog.set_level(logging.INFO, logger="apps.deduplication.decisions")

    with (
        CaptureQueriesContext(connection) as queries,
        django_capture_on_commit_callbacks(execute=True) as callbacks,
        pytest.raises(ValidationError, match="same owner"),
    ):
        decide("confirmed", candidate, owner)

    assert not any(
        q["sql"].startswith('UPDATE "businesses_businesssourcemembership"') for q in queries
    )
    assert list(Business.objects.order_by("id").values()) == businesses
    assert list(BusinessSourceMembership.objects.order_by("id").values()) == memberships
    assert list(DuplicateCandidate.objects.order_by("id").values()) == candidates
    assert callbacks == []
    assert not caplog.records


@pytest.mark.parametrize("action", ["confirmed", "rejected"])
def test_decision_rolls_back_and_emits_only_safe_payload_after_commit(
    owner, business_factory, action, django_capture_on_commit_callbacks, caplog
):
    """Catches partial commits, premature events and leaking business/contact data to logs."""
    candidate = pair(owner, business_factory(phones=["+905321234567"]), business_factory())
    before = list(Business.objects.order_by("id").values())
    memberships = list(BusinessSourceMembership.objects.order_by("id").values())
    caplog.set_level(logging.INFO, logger="apps.deduplication.decisions")
    with django_capture_on_commit_callbacks(execute=True) as callbacks, transaction.atomic():
        decide(action, candidate, owner)
        assert not caplog.records
        transaction.set_rollback(True)
    assert callbacks == []
    assert not caplog.records
    candidate.refresh_from_db()
    assert candidate.status == "pending"
    assert list(Business.objects.order_by("id").values()) == before
    assert list(BusinessSourceMembership.objects.order_by("id").values()) == memberships

    with django_capture_on_commit_callbacks(execute=True):
        result = decide(action, candidate, owner)
        assert not caplog.records
    assert len(caplog.records) == 1
    payload = caplog.records[0].decision_payload
    assert payload == {
        "candidate_id": str(candidate.id),
        "owner_id": owner.id,
        "actor_id": owner.id,
        "left_business_id": str(candidate.left_business_id),
        "right_business_id": str(candidate.right_business_id),
        "survivor_business_id": str(result.survivor_business_id) if action == "confirmed" else None,
        "merged_business_id": str(result.merged_business_id) if action == "confirmed" else None,
        "score": 75,
        "resolution_version": candidate.resolution_version,
        "decision": action,
    }
    assert "+905321234567" not in str([log.__dict__ for log in caplog.records])
