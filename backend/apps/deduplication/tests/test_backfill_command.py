import json
import logging
import socket
from datetime import UTC, datetime, timedelta
from io import StringIO
from uuid import UUID

import pytest
from django.contrib.gis.geos import Point
from django.core.management import CommandError, call_command
from django.db import DatabaseError, IntegrityError, connection, connections

from apps.businesses.models import Business, BusinessSourceMembership, DuplicateCandidate
from apps.deduplication.services import resolve_normalized_record
from apps.sources.models import NormalizedSourceRecord

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def normalized_record_factory(normalized_record_factory):
    """Give this command's fixtures explicit chronological order unless overridden."""
    serial = 0

    def create(**kwargs):
        nonlocal serial
        serial += 1
        kwargs.setdefault(
            "fetched_at", datetime(2026, 9, 5, tzinfo=UTC) + timedelta(seconds=serial)
        )
        return normalized_record_factory(**kwargs)

    return create


def run_backfill(*args):
    output, errors = StringIO(), StringIO()
    call_command("deduplicate_businesses", *args, stdout=output, stderr=errors)
    return json.loads(output.getvalue().strip().splitlines()[-1]), errors.getvalue()


def command_module():
    from apps.deduplication.management.commands import deduplicate_businesses

    return deduplicate_businesses


def test_command_is_discoverable():
    """Catches an unregistered command and missing zero-work summary fields."""
    summary, errors = run_backfill()
    assert summary == {
        "examined": 0,
        "created_businesses": 0,
        "automatic_attachments": 0,
        "pending_candidates": 0,
        "already_resolved": 0,
        "failures": 0,
    }
    assert errors == ""


def test_iteration_is_owner_then_normalized_time_then_uuid(
    owner, other_owner, normalized_record_factory, monkeypatch
):
    """Catches unstable selection order, which changes the canonical seed/winner."""
    late = normalized_record_factory(source_code="late", normalized_id=UUID(int=1))
    high = normalized_record_factory(source_code="high", normalized_id=UUID(int=3))
    low = normalized_record_factory(source_code="low", normalized_id=UUID(int=2))
    other = normalized_record_factory(source_code="other", normalized_id=UUID(int=4))
    other.source_record.campaign.created_by = other_owner
    other.source_record.campaign.save(update_fields=["created_by"])
    NormalizedSourceRecord.objects.filter(id__in=[high.id, low.id]).update(
        normalized_at=datetime(2026, 1, 2, tzinfo=UTC)
    )
    NormalizedSourceRecord.objects.filter(id=other.id).update(
        normalized_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
    seen = []

    def resolve(record_id):
        seen.append(record_id)
        return resolve_normalized_record(record_id)

    monkeypatch.setattr(command_module(), "resolve_normalized_record", resolve)
    run_backfill("--batch-size", "2")

    assert owner.id < other_owner.id
    assert seen == [low.id, high.id, late.id, other.id]
    assert BusinessSourceMembership.objects.count() == 4


def test_owner_filter_uses_current_user_primary_key(owner, other_owner, normalized_record_factory):
    """Catches ignored --owner filters or parsing current integer owner IDs as UUIDs."""
    included = normalized_record_factory(source_code="included")
    excluded = normalized_record_factory(source_code="excluded")
    excluded.source_record.campaign.created_by = other_owner
    excluded.source_record.campaign.save(update_fields=["created_by"])

    summary, _ = run_backfill("--owner", str(owner.id))

    assert summary["examined"] == 1
    assert list(
        BusinessSourceMembership.objects.values_list("normalized_record_id", flat=True)
    ) == [included.id]


@pytest.mark.parametrize("value", ["0", "-1"])
def test_batch_size_must_be_positive(value, normalized_record_factory):
    """Catches zero/negative sizes silently skipping records or creating unbounded batches."""
    normalized_record_factory(source_code="unresolved")
    with pytest.raises(CommandError, match="positive"):
        run_backfill("--batch-size", value)
    assert not Business.objects.exists()


@pytest.mark.parametrize("dry_run", [False, True])
def test_exact_summary_uses_real_resolution_outcomes(dry_run, normalized_record_factory):
    """Catches incorrect seeded/source-identity/automatic/candidate outcome accounting."""
    first = normalized_record_factory(source_code="same", phones=["+905321234567"])
    identity = normalized_record_factory(source_code="same", phones=first.phones)
    identity.source_record.external_id = first.source_record.external_id
    identity.source_record.save(update_fields=["external_id"])
    normalized_record_factory(source_code="automatic", phones=first.phones)
    normalized_record_factory(source_code="review", phones=first.phones, location=Point(30, 35))

    summary, errors = run_backfill("--batch-size", "2", *(["--dry-run"] if dry_run else []))

    assert summary == {
        "examined": 4,
        "created_businesses": 2,
        "automatic_attachments": 2,
        "pending_candidates": 1,
        "already_resolved": 0,
        "failures": 0,
    }
    assert errors == ""
    assert Business.objects.count() == (0 if dry_run else 2)
    assert BusinessSourceMembership.objects.count() == (0 if dry_run else 4)
    assert DuplicateCandidate.objects.count() == (0 if dry_run else 1)


def test_each_real_batch_commits_before_next_batch(normalized_record_factory, monkeypatch):
    """Catches one transaction per record or one transaction around the entire real run."""
    for index in range(5):
        normalized_record_factory(source_code=f"record-{index}")
    committed_counts = []
    observer = connection.copy(alias="backfill_observer")
    connections["backfill_observer"] = observer

    def resolve(record_id):
        with observer.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM businesses_businesssourcemembership")
            committed_counts.append(cursor.fetchone()[0])
        return resolve_normalized_record(record_id)

    monkeypatch.setattr(command_module(), "resolve_normalized_record", resolve)
    try:
        summary, errors = run_backfill("--batch-size", "2")
    finally:
        observer.close()
        del connections["backfill_observer"]

    assert errors == ""
    assert committed_counts == [0, 0, 2, 2, 4]
    assert summary["examined"] == BusinessSourceMembership.objects.count() == 5


def test_failed_record_rolls_back_without_losing_batch_successes(
    normalized_record_factory, monkeypatch, caplog
):
    """Catches partial failed-record writes, poisoned transactions, and lost batch successes."""
    records = [
        normalized_record_factory(source_code=f"record-{index}", phones=["+905321234567"])
        for index in range(3)
    ]
    caplog.set_level(logging.INFO, logger="common.observability")

    def resolve(record_id):
        result = resolve_normalized_record(record_id)
        if record_id == records[1].id:
            raise IntegrityError("forced failure after resolver writes")
        return result

    monkeypatch.setattr(command_module(), "resolve_normalized_record", resolve)
    summary, errors = run_backfill("--batch-size", "3")

    assert summary == {
        "examined": 3,
        "created_businesses": 1,
        "automatic_attachments": 1,
        "pending_candidates": 0,
        "already_resolved": 0,
        "failures": 1,
    }
    assert str(records[1].id) in errors
    assert "IntegrityError" in errors
    assert set(BusinessSourceMembership.objects.values_list("normalized_record_id", flat=True)) == {
        records[0].id,
        records[2].id,
    }
    assert len(caplog.records) == 2

    monkeypatch.setattr(command_module(), "resolve_normalized_record", resolve_normalized_record)
    resumed, _ = run_backfill()
    assert resumed["examined"] == resumed["automatic_attachments"] == 1
    assert BusinessSourceMembership.objects.count() == 3


def test_commit_failure_preserves_earlier_batches_and_can_resume(
    normalized_record_factory, monkeypatch
):
    """Catches rollback of earlier batches or skipped unresolved rows after a fatal commit."""
    records = [normalized_record_factory(source_code=f"record-{index}") for index in range(5)]
    real_commit = connection.commit
    commits = 0

    def fail_second_commit():
        nonlocal commits
        commits += 1
        if commits == 2:
            raise DatabaseError("forced batch commit failure")
        real_commit()

    with monkeypatch.context() as patch:
        patch.setattr(connection, "commit", fail_second_commit)
        with pytest.raises(DatabaseError, match="forced batch commit failure"):
            run_backfill("--batch-size", "2")

    assert set(BusinessSourceMembership.objects.values_list("normalized_record_id", flat=True)) == {
        records[0].id,
        records[1].id,
    }
    summary, _ = run_backfill("--batch-size", "2")
    assert summary["examined"] == 3
    assert summary["failures"] == 0
    assert BusinessSourceMembership.objects.count() == 5


def test_savepoint_rollback_failure_aborts_instead_of_reporting_rolled_back_successes(
    normalized_record_factory, monkeypatch
):
    """Catches continuing a poisoned batch when per-record isolation cannot be guaranteed."""
    records = [normalized_record_factory(source_code=f"record-{index}") for index in range(4)]

    def resolve(record_id):
        result = resolve_normalized_record(record_id)
        if record_id == records[2].id:
            raise IntegrityError("forced record failure")
        return result

    def fail_rollback(savepoint_id):
        raise DatabaseError("savepoint rollback unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(command_module(), "resolve_normalized_record", resolve)
        patch.setattr(connection, "savepoint_rollback", fail_rollback)
        with pytest.raises(IntegrityError, match="forced record failure"):
            run_backfill("--batch-size", "2")

    assert set(BusinessSourceMembership.objects.values_list("normalized_record_id", flat=True)) == {
        records[0].id,
        records[1].id,
    }
    summary, _ = run_backfill("--batch-size", "2")
    assert summary["examined"] == 2
    assert BusinessSourceMembership.objects.count() == 4


def test_dry_run_restores_existing_materialization_and_suppresses_events(
    normalized_record_factory, caplog
):
    """Catches dry-run canonical edits, surviving candidates, and premature on_commit events."""
    first = normalized_record_factory(source_code="first", phones=["+905321234567"])
    resolve_normalized_record(first.id)
    normalized_record_factory(
        source_code="attachment", phones=first.phones, emails=["new@example.test"]
    )
    normalized_record_factory(source_code="review", phones=first.phones, location=Point(30, 35))
    models = (Business, BusinessSourceMembership, DuplicateCandidate, NormalizedSourceRecord)
    before = [list(model.objects.order_by("pk").values()) for model in models]
    caplog.clear()
    caplog.set_level(logging.INFO, logger="common.observability")

    summary, _ = run_backfill("--dry-run", "--batch-size", "1")

    assert summary["examined"] == 2
    assert summary["automatic_attachments"] == summary["created_businesses"] == 1
    assert summary["pending_candidates"] == 1
    assert [list(model.objects.order_by("pk").values()) for model in models] == before
    assert not caplog.records


def test_second_execution_skips_resolved_rows(normalized_record_factory):
    """Catches replay creating memberships/candidates or needlessly re-resolving existing rows."""
    normalized_record_factory(source_code="first")
    run_backfill()
    before = list(Business.objects.values())

    summary, _ = run_backfill()

    assert summary == {
        "examined": 0,
        "created_businesses": 0,
        "automatic_attachments": 0,
        "pending_candidates": 0,
        "already_resolved": 0,
        "failures": 0,
    }
    assert list(Business.objects.values()) == before
    assert BusinessSourceMembership.objects.count() == 1


def test_concurrently_resolved_row_is_counted_as_already_resolved(
    normalized_record_factory, monkeypatch
):
    """Catches ignoring an idempotent resolver result when a selected row is already attached."""
    normalized_record_factory(source_code="racing")

    def resolve(record_id):
        resolve_normalized_record(record_id)
        return resolve_normalized_record(record_id)

    monkeypatch.setattr(command_module(), "resolve_normalized_record", resolve)
    summary, _ = run_backfill()
    assert summary == {
        "examined": 1,
        "created_businesses": 0,
        "automatic_attachments": 0,
        "pending_candidates": 0,
        "already_resolved": 1,
        "failures": 0,
    }
    assert BusinessSourceMembership.objects.count() == 1


def test_command_resolves_without_adapters_or_network(normalized_record_factory, monkeypatch):
    """Catches backfill re-running discovery or contacting external providers."""
    normalized_record_factory(source_code="offline")

    def forbidden(*args, **kwargs):
        pytest.fail("Backfill must not invoke adapters or network")

    monkeypatch.setattr("apps.discovery.registry.get_adapter", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    summary, _ = run_backfill()
    assert summary["created_businesses"] == Business.objects.count() == 1
