from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import IntegrityError, close_old_connections, transaction

from apps.campaigns.models import PipelineRetryReservation
from apps.campaigns.retries import consume_normalization_retry, consume_source_retry


@pytest.mark.django_db(transaction=True)
def test_exhausted_retry_token_is_denied_idempotently_without_counter_change(
    ready_run_with_one_pending_record,
):
    record = ready_run_with_one_pending_record.records.get()
    record.normalization_retry_count = record.source.max_retries
    record.save(update_fields=["normalization_retry_count"])

    assert (
        consume_normalization_retry(
            source_record_id=record.id,
            delivery_token="task-denied:3",
        )
        is False
    )
    assert (
        consume_normalization_retry(
            source_record_id=record.id,
            delivery_token="task-denied:3",
        )
        is False
    )

    record.refresh_from_db()
    assert record.normalization_retry_count == record.source.max_retries
    assert (
        PipelineRetryReservation.objects.filter(
            scope="source_normalization",
            work_id=record.id,
            delivery_token="task-denied:3",
            allowed=False,
        ).count()
        == 1
    )


@pytest.mark.django_db(transaction=True)
def test_concurrent_source_retry_reservation_is_single_and_db_unique_guard_holds(
    running_source_run,
):
    def reserve_once(_: int) -> bool:
        close_old_connections()
        try:
            return consume_source_retry(
                source_run_id=running_source_run.id,
                delivery_token="task-concurrent:0",
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert list(executor.map(reserve_once, range(2))) == [True, True]

    running_source_run.refresh_from_db()
    assert running_source_run.source_retry_count == 1
    reservation = PipelineRetryReservation.objects.get(
        scope="source_discovery",
        work_id=running_source_run.id,
        delivery_token="task-concurrent:0",
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        PipelineRetryReservation.objects.create(
            campaign=running_source_run.campaign,
            scope=reservation.scope,
            work_id=reservation.work_id,
            delivery_token=reservation.delivery_token,
            allowed=True,
        )


@pytest.mark.django_db(transaction=True)
def test_same_normalization_delivery_token_reserves_budget_once(
    ready_run_with_one_pending_record,
):
    record = ready_run_with_one_pending_record.records.get()

    assert consume_normalization_retry(
        source_record_id=record.id,
        delivery_token="task-99:0",
    )
    assert consume_normalization_retry(
        source_record_id=record.id,
        delivery_token="task-99:0",
    )

    record.refresh_from_db()
    assert record.normalization_retry_count == 1
    assert (
        PipelineRetryReservation.objects.filter(
            scope="source_normalization",
            work_id=record.id,
            delivery_token="task-99:0",
        ).count()
        == 1
    )


@pytest.mark.django_db(transaction=True)
def test_exhausted_source_retry_is_denied_without_changing_counter(running_source_run):
    running_source_run.source_retry_count = running_source_run.source.max_retries
    running_source_run.save(update_fields=("source_retry_count",))

    assert not consume_source_retry(
        source_run_id=running_source_run.id,
        delivery_token="source-denied:3",
    )

    running_source_run.refresh_from_db()
    assert running_source_run.source_retry_count == running_source_run.source.max_retries
