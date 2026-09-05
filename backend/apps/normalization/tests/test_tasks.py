from unittest.mock import Mock, patch

import pytest
from celery.exceptions import Retry
from django.db import OperationalError

from apps.campaigns.progress import get_campaign_progress
from apps.normalization.tasks import (
    fail_source_record_once,
    normalize_source_record,
    normalize_source_record_now,
)
from apps.sources.models import SourceRecord
from apps.sources.storage import RawStorageUnavailable


@pytest.mark.django_db(transaction=True)
def test_last_normalized_record_completes_source_run_and_campaign(
    source_run_with_two_records,
):
    first, second = source_run_with_two_records.records.order_by("created_at")

    normalize_source_record_now(first.id)
    assert (
        get_campaign_progress(
            source_run_with_two_records.campaign_id,
            actor=source_run_with_two_records.campaign.created_by,
        ).totals.normalized
        == 1
    )
    normalize_source_record_now(second.id)

    source_run_with_two_records.refresh_from_db()
    source_run_with_two_records.campaign.refresh_from_db()
    assert source_run_with_two_records.status == "completed"
    assert source_run_with_two_records.campaign.status == "completed"


@pytest.mark.django_db(transaction=True)
def test_retrying_normalization_does_not_double_count(one_pending_record):
    normalize_source_record_now(one_pending_record.id)
    normalize_source_record_now(one_pending_record.id)

    run = one_pending_record.source_run
    run.refresh_from_db()
    assert run.normalized_records == 1


@pytest.mark.django_db(transaction=True)
def test_exhausted_normalization_marks_pending_record_failed_once(
    ready_run_with_one_pending_record,
):
    record = ready_run_with_one_pending_record.records.get()

    assert fail_source_record_once(
        source_record_id=record.id,
        error_code="RAW_STORAGE_UNAVAILABLE",
    )
    assert not fail_source_record_once(
        source_record_id=record.id,
        error_code="RAW_STORAGE_UNAVAILABLE",
    )

    record.refresh_from_db()
    ready_run_with_one_pending_record.refresh_from_db()
    assert record.normalization_status == "failed"
    assert record.normalization_error_code == "RAW_STORAGE_UNAVAILABLE"
    assert ready_run_with_one_pending_record.failed_records == 1
    assert ready_run_with_one_pending_record.status == "completed_with_errors"


@pytest.mark.django_db(transaction=True)
def test_exhausted_normalization_budget_fails_record_once_without_retry(
    ready_run_with_one_pending_record,
    monkeypatch,
):
    record = ready_run_with_one_pending_record.records.get()
    record.normalization_retry_count = record.source.max_retries
    record.save(update_fields=["normalization_retry_count"])
    monkeypatch.setattr(
        "apps.normalization.tasks.normalize_source_record_now",
        Mock(side_effect=RawStorageUnavailable()),
    )
    with patch.object(normalize_source_record, "retry") as retry:
        normalize_source_record.run(str(record.id))

    retry.assert_not_called()
    record.refresh_from_db()
    ready_run_with_one_pending_record.refresh_from_db()
    ready_run_with_one_pending_record.campaign.refresh_from_db()
    assert record.normalization_status == SourceRecord.NormalizationStatus.FAILED
    assert record.normalization_error_code == "RAW_STORAGE_UNAVAILABLE"
    assert ready_run_with_one_pending_record.failed_records == 1
    assert ready_run_with_one_pending_record.status == "completed_with_errors"
    assert ready_run_with_one_pending_record.campaign.status == "completed_with_errors"


@pytest.mark.django_db(transaction=True)
def test_database_retry_does_not_spend_normalization_storage_budget(
    ready_run_with_one_pending_record,
    monkeypatch,
):
    record = ready_run_with_one_pending_record.records.get()
    core = Mock(side_effect=[OperationalError("database unavailable"), RawStorageUnavailable()])
    monkeypatch.setattr("apps.normalization.tasks.normalize_source_record_now", core)

    with (
        patch.object(normalize_source_record, "retry", side_effect=Retry()),
        pytest.raises(Retry),
    ):
        normalize_source_record.run(str(record.id))
    record.refresh_from_db()
    assert record.normalization_retry_count == 0

    with (
        patch.object(normalize_source_record, "retry", side_effect=Retry()) as retry,
        pytest.raises(Retry),
    ):
        normalize_source_record.run(str(record.id))
    record.refresh_from_db()
    assert record.normalization_retry_count == 1
    assert record.normalization_status == SourceRecord.NormalizationStatus.PENDING
    retry.assert_called_once()
    assert "max_retries" not in retry.call_args.kwargs
