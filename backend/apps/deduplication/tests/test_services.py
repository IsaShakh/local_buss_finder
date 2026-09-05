import logging

import pytest
from django.contrib.gis.geos import Point
from django.db import connection, transaction

from apps.businesses.models import Business, BusinessSourceMembership, DuplicateCandidate
from apps.deduplication.materialization import seed_business
from apps.taxonomy.models import BusinessCategory

pytestmark = pytest.mark.django_db


def resolve(record):
    from apps.deduplication.services import resolve_normalized_record

    return resolve_normalized_record(record.id)


def test_seed_and_replay_are_idempotent(owner, normalized_record_factory):
    """Catches duplicate canonical rows or replay changing recorded attachment evidence."""
    record = normalized_record_factory(source_code="seed")
    first = resolve(record)
    replay = resolve(record)

    assert first.action == "seeded"
    assert replay.action == "already_resolved"
    assert replay.business_id == first.business_id
    assert replay.membership_id == first.membership_id
    assert replay.candidate_ids == ()
    assert Business.objects.count() == BusinessSourceMembership.objects.count() == 1
    business = Business.objects.get(id=first.business_id)
    assert business.owner_id == owner.id
    assert business.primary_normalized_record_id == record.id


def test_source_identity_overrides_conflicting_details(owner, normalized_record_factory):
    """Catches applying fuzzy automatic gates to exact provider identities."""
    first = normalized_record_factory(source_code="same")
    business = seed_business(normalized_record=first, owner_id=owner.id)
    incoming = normalized_record_factory(
        source_code="same", match_name="different", location=Point(30, 35)
    )
    incoming.source_record.external_id = first.source_record.external_id
    incoming.source_record.save(update_fields=["external_id"])

    outcome = resolve(incoming)

    assert outcome.action == "source_identity"
    assert outcome.business_id == business.id
    membership = BusinessSourceMembership.objects.get(id=outcome.membership_id)
    assert membership.match_score == 100
    assert membership.match_signals == [{"code": "source_identity", "weight": 100, "value": None}]


@pytest.mark.parametrize("gate", ["phone", "domain", "exact_details"])
def test_automatic_gates_attach_and_rebuild(owner, normalized_record_factory, gate):
    """Catches missing contact/detail gate attachments and forgotten materialization."""
    category = BusinessCategory.objects.create(name="Clinic", slug="clinic")
    contacts = {"phones": ["+905321234567"]} if gate == "phone" else {}
    if gate == "domain":
        contacts = {"websites": ["https://clinic.test"]}
    first = normalized_record_factory(source_code="first", category=category, **contacts)
    business = seed_business(normalized_record=first, owner_id=owner.id)
    incoming = normalized_record_factory(
        source_code="second", category=category, emails=["new@clinic.test"], **contacts
    )

    outcome = resolve(incoming)

    assert outcome.action == "automatic"
    assert outcome.business_id == business.id
    business.refresh_from_db()
    assert business.emails == ["new@clinic.test"]
    assert business.memberships.count() == 2


def test_winner_is_score_then_uuid_and_bridge_never_merges_businesses(
    owner, normalized_record_factory
):
    """Catches nondeterministic winners and transitive merging through shared contacts."""
    category = BusinessCategory.objects.create(name="Clinic", slug="clinic")
    records = [
        normalized_record_factory(
            source_code=f"existing-{index}", category=category, phones=["+905321234567"]
        )
        for index in range(3)
    ]
    businesses = [seed_business(normalized_record=row, owner_id=owner.id) for row in records]
    ordered = sorted(businesses, key=lambda business: str(business.id))
    # Lower UUID cannot override a lower score (90 versus 100).
    ordered[0].address_text = ""
    ordered[0].category = None
    ordered[0].save(update_fields=["address_text", "category"])
    incoming = normalized_record_factory(
        source_code="bridge", category=category, phones=["+905321234567"]
    )

    outcome = resolve(incoming)

    assert outcome.business_id == ordered[1].id
    assert Business.active.count() == 3
    assert ordered[0].memberships.count() == ordered[2].memberships.count() == 1
    assert ordered[1].memberships.count() == 2
    candidates = list(DuplicateCandidate.objects.order_by("-score"))
    assert len(candidates) == len(outcome.candidate_ids) == 2
    assert {candidate.score for candidate in candidates} == {90, 100}
    for candidate in candidates:
        assert candidate.owner_id == owner.id
        assert candidate.left_business_id < candidate.right_business_id
        assert ordered[1].id in (candidate.left_business_id, candidate.right_business_id)
        assert candidate.status == "pending"


@pytest.mark.parametrize(("name", "expected_count"), [("alanya smile", 1), ("unrelated", 0)])
def test_nonautomatic_matches_seed_and_review_only_scores_at_least_55(
    owner, normalized_record_factory, name, expected_count
):
    """Catches attachment from score alone and review rows below the score floor."""
    first = normalized_record_factory(
        source_code="first", phones=["+905321234567"], address_text=""
    )
    seed_business(normalized_record=first, owner_id=owner.id)
    incoming = normalized_record_factory(
        source_code="second",
        phones=first.phones,
        match_name=name,
        address_text="",
        location=Point(30, 35),
    )

    outcome = resolve(incoming)

    assert outcome.action == "seeded"
    assert Business.active.count() == 2
    assert DuplicateCandidate.objects.count() == len(outcome.candidate_ids) == expected_count
    if expected_count:
        assert DuplicateCandidate.objects.get().score == 65


def test_review_includes_exactly_55_without_automatic_gate(owner, normalized_record_factory):
    """Catches a strict rather than inclusive review score boundary."""
    first = normalized_record_factory(source_code="first", address_text="")
    seed_business(normalized_record=first, owner_id=owner.id)
    incoming = normalized_record_factory(source_code="second", address_text="")

    outcome = resolve(incoming)

    assert outcome.action == "seeded"
    candidate = DuplicateCandidate.objects.get()
    assert candidate.score == 55
    assert outcome.candidate_ids == (candidate.id,)


@pytest.mark.parametrize("status", ["pending", "rejected", "confirmed", "superseded"])
def test_existing_pair_refreshes_only_while_pending(owner, normalized_record_factory, status):
    """Catches update_or_create silently reopening terminal decisions."""
    first = normalized_record_factory(source_code="first", phones=["+905321234567"])
    second = normalized_record_factory(
        source_code="second", phones=first.phones, location=Point(30, 35)
    )
    left = seed_business(normalized_record=first, owner_id=owner.id)
    right = seed_business(normalized_record=second, owner_id=owner.id)
    left_id, right_id = DuplicateCandidate.ordered_pair(left.id, right.id)
    existing = DuplicateCandidate(
        owner=owner,
        left_business_id=left_id,
        right_business_id=right_id,
        score=55,
        signals=[{"code": "old", "weight": 55}],
        status=status,
    )
    existing.full_clean()
    existing.save()
    incoming = normalized_record_factory(source_code="incoming", phones=first.phones)

    outcome = resolve(incoming)

    assert outcome.business_id == left.id
    existing.refresh_from_db()
    assert existing.status == status
    assert DuplicateCandidate.objects.count() == 1
    if status == "pending":
        assert existing.score == 85
        assert outcome.candidate_ids == (existing.id,)
    else:
        assert existing.score == 55
        assert existing.signals == [{"code": "old", "weight": 55}]
        assert outcome.candidate_ids == ()


def test_resolution_rolls_back_with_outer_transaction_and_defers_contact_free_events(
    normalized_record_factory, django_capture_on_commit_callbacks, caplog
):
    """Catches independent resolver commits or premature/contact-bearing resolution events."""
    caplog.set_level(logging.INFO, logger="common.observability")
    record = normalized_record_factory(source_code="incoming", phones=["+905321234567"])
    with django_capture_on_commit_callbacks(execute=True) as callbacks, transaction.atomic():
        resolve(record)
        assert not caplog.records
        transaction.set_rollback(True)
    assert callbacks == []
    assert not BusinessSourceMembership.objects.exists()
    assert not Business.objects.exists()

    with django_capture_on_commit_callbacks(execute=True):
        resolve(record)
        assert not caplog.records
    assert caplog.records
    assert "+905321234567" not in str([log.__dict__ for log in caplog.records])


@pytest.mark.django_db(transaction=True)
def test_owner_lock_requires_transaction_and_uses_transaction_advisory_lock(owner):
    """Catches session locks, missing transactions, and locks not acquired at all."""
    from apps.deduplication.locks import owner_resolution_lock

    with pytest.raises(AssertionError), owner_resolution_lock(owner.id):
        pass
    with transaction.atomic(), owner_resolution_lock(owner.id), connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
            "AND pid = pg_backend_pid() AND granted AND objsubid = 2"
        )
        assert cursor.fetchone()[0] == 1
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND pid = pg_backend_pid()"
        )
        assert cursor.fetchone()[0] == 0
