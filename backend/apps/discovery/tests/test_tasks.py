from unittest.mock import Mock, patch

import pytest
from celery.exceptions import OperationalError as BrokerOperationalError
from celery.exceptions import Reject, Retry
from django.db import OperationalError

from apps.campaigns.models import CampaignSourceRun, PipelineRetryReservation
from apps.discovery.errors import PermanentSourceError, TransientSourceError
from apps.discovery.tasks import run_source_discovery
from apps.normalization.tasks import fail_source_record_once


@pytest.mark.django_db(transaction=True)
def test_campaign_task_transitions_once_and_enqueues_pending_runs(
    single_source_draft_campaign,
    owner,
    monkeypatch,
):
    from apps.campaigns.models import DiscoveryCampaign
    from apps.campaigns.services import start_campaign
    from apps.discovery.tasks import run_discovery_campaign

    campaign = start_campaign(
        campaign_id=single_source_draft_campaign.id,
        actor=owner,
        enqueue=lambda _: None,
    )
    queued = []
    monkeypatch.setattr(
        "apps.discovery.tasks.run_source_discovery.delay",
        lambda source_run_id: queued.append(source_run_id),
    )

    run_discovery_campaign.run(str(campaign.id))
    run_discovery_campaign.run(str(campaign.id))

    campaign.refresh_from_db()
    assert campaign.status == DiscoveryCampaign.Status.RUNNING
    assert campaign.started_at is not None
    assert queued == [str(campaign.source_runs.get().id)]


@pytest.mark.django_db(transaction=True)
def test_transient_source_error_consumes_one_durable_retry_and_retries(
    running_source_run,
    monkeypatch,
):
    monkeypatch.setattr(
        "apps.discovery.tasks.run_source_discovery_now",
        Mock(side_effect=TransientSourceError("SOURCE_TIMEOUT")),
    )
    with (
        patch.object(run_source_discovery, "retry", side_effect=Retry()) as retry,
        pytest.raises(Retry),
    ):
        run_source_discovery.run(str(running_source_run.id))

    running_source_run.refresh_from_db()
    assert running_source_run.source_retry_count == 1
    assert running_source_run.status == CampaignSourceRun.Status.RUNNING
    retry.assert_called_once()
    assert "max_retries" not in retry.call_args.kwargs


@pytest.mark.django_db(transaction=True)
def test_retry_publish_failure_redelivery_reuses_the_same_reservation(
    running_source_run,
    monkeypatch,
):
    monkeypatch.setattr(
        "apps.discovery.tasks.run_source_discovery_now",
        Mock(side_effect=TransientSourceError("SOURCE_TIMEOUT")),
    )
    monkeypatch.setattr(
        "apps.discovery.tasks.make_delivery_token",
        Mock(return_value="task-42:0"),
    )
    with (
        patch.object(
            run_source_discovery,
            "retry",
            side_effect=BrokerOperationalError("retry publish failed"),
        ),
        pytest.raises(Reject) as rejected,
    ):
        run_source_discovery.run(str(running_source_run.id))
    assert rejected.value.requeue is True
    running_source_run.refresh_from_db()
    assert running_source_run.source_retry_count == 1
    assert (
        PipelineRetryReservation.objects.filter(
            scope="source_discovery",
            work_id=running_source_run.id,
            delivery_token="task-42:0",
            allowed=True,
        ).count()
        == 1
    )

    with (
        patch.object(run_source_discovery, "retry", side_effect=Retry()),
        pytest.raises(Retry),
    ):
        run_source_discovery.run(str(running_source_run.id))
    running_source_run.refresh_from_db()
    assert running_source_run.source_retry_count == 1
    assert running_source_run.status == CampaignSourceRun.Status.RUNNING


@pytest.mark.django_db(transaction=True)
def test_exhausted_source_budget_marks_empty_run_failed_without_retry(
    running_source_run,
    monkeypatch,
):
    running_source_run.source_retry_count = running_source_run.source.max_retries
    running_source_run.save(update_fields=["source_retry_count"])
    monkeypatch.setattr(
        "apps.discovery.tasks.run_source_discovery_now",
        Mock(side_effect=TransientSourceError("SOURCE_TIMEOUT")),
    )
    with patch.object(run_source_discovery, "retry") as retry:
        run_source_discovery.run(str(running_source_run.id))

    retry.assert_not_called()
    running_source_run.refresh_from_db()
    running_source_run.campaign.refresh_from_db()
    assert running_source_run.discovery_finished_at is not None
    assert running_source_run.status == CampaignSourceRun.Status.FAILED
    assert running_source_run.failed_records == 0
    assert running_source_run.campaign.failed_jobs == 1


@pytest.mark.django_db(transaction=True)
def test_database_retry_does_not_spend_source_business_budget(
    running_source_run,
    monkeypatch,
):
    core = Mock(
        side_effect=[
            OperationalError("database unavailable"),
            TransientSourceError("SOURCE_TIMEOUT"),
        ]
    )
    monkeypatch.setattr("apps.discovery.tasks.run_source_discovery_now", core)

    with (
        patch.object(run_source_discovery, "retry", side_effect=Retry()),
        pytest.raises(Retry),
    ):
        run_source_discovery.run(str(running_source_run.id))
    running_source_run.refresh_from_db()
    assert running_source_run.source_retry_count == 0

    with (
        patch.object(run_source_discovery, "retry", side_effect=Retry()),
        pytest.raises(Retry),
    ):
        run_source_discovery.run(str(running_source_run.id))
    running_source_run.refresh_from_db()
    assert running_source_run.source_retry_count == 1


@pytest.mark.django_db(transaction=True)
def test_permanent_source_error_fails_without_retry(running_source_run, monkeypatch):
    monkeypatch.setattr(
        "apps.discovery.tasks.run_source_discovery_now",
        Mock(side_effect=PermanentSourceError("INVALID_SOURCE_PAYLOAD")),
    )
    with patch.object(run_source_discovery, "retry") as retry:
        run_source_discovery.run(str(running_source_run.id))

    retry.assert_not_called()
    running_source_run.refresh_from_db()
    assert running_source_run.status == CampaignSourceRun.Status.FAILED
    assert running_source_run.error_code == "INVALID_SOURCE_PAYLOAD"


@pytest.mark.django_db(transaction=True)
def test_exhausted_source_waits_for_its_pending_record_before_terminal_status(
    running_source_run_with_pending_record,
    monkeypatch,
):
    run = running_source_run_with_pending_record
    run.source_retry_count = run.source.max_retries
    run.save(update_fields=["source_retry_count"])
    monkeypatch.setattr(
        "apps.discovery.tasks.run_source_discovery_now",
        Mock(side_effect=TransientSourceError("SOURCE_TIMEOUT")),
    )
    with patch.object(run_source_discovery, "retry") as retry:
        run_source_discovery.run(str(run.id))

    retry.assert_not_called()
    run.refresh_from_db()
    run.campaign.refresh_from_db()
    assert run.discovery_finished_at is not None
    assert run.status == CampaignSourceRun.Status.NORMALIZING
    assert run.campaign.completed_jobs == 0
    record = run.records.get(normalization_status="pending")

    assert fail_source_record_once(
        source_record_id=record.id,
        error_code="NORMALIZATION_ERROR",
    )
    run.refresh_from_db()
    run.campaign.refresh_from_db()
    assert run.status == CampaignSourceRun.Status.COMPLETED_WITH_ERRORS
    assert run.campaign.status == "completed_with_errors"
