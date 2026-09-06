from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Barrier
from time import monotonic, sleep

import pytest
from django.db import connection, connections, transaction

from apps.businesses.models import Business, BusinessSourceMembership, DuplicateCandidate
from apps.deduplication.candidates import find_candidate_businesses
from apps.deduplication.locks import owner_resolution_lock
from apps.deduplication.materialization import seed_business
from apps.deduplication.services import resolve_normalized_record

pytestmark = pytest.mark.django_db(transaction=True)


def _resolve_in_worker(record_id, barrier, pids):
    """Use a dedicated real connection with bounded waits and guaranteed cleanup."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET lock_timeout = '10s'")
            cursor.execute("SET statement_timeout = '15s'")
            cursor.execute("SELECT pg_backend_pid()")
            pids.put(cursor.fetchone()[0])
        barrier.wait(timeout=5)
        return resolve_normalized_record(record_id)
    finally:
        connections.close_all()


def test_two_workers_resolve_one_unresolved_record_once(owner, normalized_record_factory):
    """Catches races that create orphan businesses or duplicate membership attempts."""
    assert connection.vendor == "postgresql"
    record = normalized_record_factory(source_code="incoming")
    assert not BusinessSourceMembership.objects.filter(normalized_record=record).exists()
    barrier = Barrier(2)
    pids = Queue()

    with ThreadPoolExecutor(max_workers=2) as executor:
        # Hold the actual owner lock until both database sessions are observed
        # waiting on it, so this cannot silently become a sequential replay test.
        with transaction.atomic(), owner_resolution_lock(owner.id):
            futures = [
                executor.submit(_resolve_in_worker, record.id, barrier, pids) for _ in range(2)
            ]
            worker_pids = [pids.get(timeout=5), pids.get(timeout=5)]
            assert len(set(worker_pids)) == 2
            deadline = monotonic() + 5
            waiting = 0
            while monotonic() < deadline:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
                        "AND NOT granted AND pid IN (%s, %s)",
                        worker_pids,
                    )
                    waiting = cursor.fetchone()[0]
                if waiting == 2:
                    break
                sleep(0.01)
            assert waiting == 2, "Both workers must contend on the owner's PostgreSQL lock"
        outcomes = [future.result(timeout=15) for future in futures]

    assert sorted(outcome.action for outcome in outcomes) == ["already_resolved", "seeded"]
    assert len({outcome.membership_id for outcome in outcomes}) == 1
    assert len({outcome.business_id for outcome in outcomes}) == 1
    assert Business.objects.count() == Business.active.count() == 1
    membership = BusinessSourceMembership.objects.get()
    assert membership.normalized_record_id == record.id
    assert membership.business_id == outcomes[0].business_id
    assert membership.business.owner_id == owner.id
    assert not DuplicateCandidate.objects.exists()


def test_concurrent_owners_only_attach_and_compare_with_their_own_businesses(
    owner, other_owner, normalized_record_factory
):
    """Catches cross-owner candidate scoring/attachment even with identical evidence."""
    assert connection.vendor == "postgresql"
    expected = []
    incoming_records = []
    for actor in (owner, other_owner):
        existing = normalized_record_factory(
            source_code=f"seed-{actor.id}", phones=["+905321234567"]
        )
        incoming = normalized_record_factory(
            source_code=f"new-{actor.id}", phones=["+905321234567"]
        )
        for record in (existing, incoming):
            campaign = record.source_record.campaign
            campaign.created_by = actor
            campaign.save(update_fields=["created_by"])
        expected.append(seed_business(normalized_record=existing, owner_id=actor.id))
        incoming_records.append(incoming)

    for incoming, business in zip(incoming_records, expected, strict=True):
        matches = find_candidate_businesses(normalized_record=incoming)
        assert [match.business_id for match in matches] == [business.id]

    barrier = Barrier(2)
    pids = Queue()
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(_resolve_in_worker, record.id, barrier, pids)
            for record in incoming_records
        ]
        outcomes = [future.result(timeout=20) for future in futures]
    assert pids.get(timeout=1) != pids.get(timeout=1)

    for outcome, business, incoming in zip(outcomes, expected, incoming_records, strict=True):
        assert outcome.action == "automatic"
        assert outcome.business_id == business.id
        assert outcome.candidate_ids == ()
        membership = BusinessSourceMembership.objects.get(normalized_record=incoming)
        assert membership.business_id == business.id
        assert business.memberships.count() == 2
    assert Business.objects.count() == Business.active.count() == 2
    assert BusinessSourceMembership.objects.count() == 4
    assert not DuplicateCandidate.objects.exists()
