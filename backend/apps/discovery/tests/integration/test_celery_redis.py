import time
from threading import Event
from uuid import uuid4

import pytest
from celery.contrib.testing.worker import start_worker
from celery.signals import task_postrun
from django.db import close_old_connections

from apps.campaigns.models import CampaignSourceRun, DiscoveryCampaign
from apps.campaigns.services import start_campaign
from apps.discovery.tasks import run_discovery_campaign
from apps.sources.models import NormalizedSourceRecord, SourceRecord
from config.celery import app as celery_app


def wait_until(predicate, *, description: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        close_old_connections()
        if predicate():
            return
        time.sleep(0.1)
    raise AssertionError(f"Timeout while waiting for {description}")


@pytest.mark.django_db(transaction=True)
@pytest.mark.integration
def test_real_redis_keeps_normalization_work_until_worker_returns(owner, alanya_campaign):
    assert celery_app.conf.task_always_eager is False
    assert celery_app.conf.task_routes["apps.discovery.tasks.*"]["queue"] == "discovery"
    assert celery_app.conf.task_routes["apps.normalization.tasks.*"]["queue"] == "normalization"
    celery_app.control.purge()

    captured_root_ids: list[str] = []
    start_campaign(
        campaign_id=alanya_campaign.id,
        actor=owner,
        enqueue=lambda campaign_id: captured_root_ids.append(str(campaign_id)),
    )
    assert captured_root_ids == [str(alanya_campaign.id)]

    def discovery_has_finished() -> bool:
        runs = list(
            CampaignSourceRun.objects.filter(campaign=alanya_campaign)
            .order_by("source__code")
            .values("discovery_finished_at", "stored_records")
        )
        return len(runs) == 2 and all(
            row["discovery_finished_at"] is not None and row["stored_records"] == 3 for row in runs
        )

    with start_worker(
        celery_app,
        queues=["discovery"],
        pool="solo",
        concurrency=1,
        perform_ping_check=False,
    ):
        run_discovery_campaign.delay(str(alanya_campaign.id))
        wait_until(discovery_has_finished, description="both discovery source runs")

    alanya_campaign.refresh_from_db()
    assert alanya_campaign.status == DiscoveryCampaign.Status.RUNNING
    assert alanya_campaign.raw_records_found == 6
    assert alanya_campaign.normalized_records == 0
    assert SourceRecord.objects.filter(campaign=alanya_campaign).count() == 6

    with start_worker(
        celery_app,
        queues=["normalization"],
        pool="solo",
        concurrency=1,
        perform_ping_check=False,
    ):
        wait_until(
            lambda: DiscoveryCampaign.objects.filter(
                id=alanya_campaign.id,
                status=DiscoveryCampaign.Status.COMPLETED,
                normalized_records=6,
            ).exists(),
            description="normalization and campaign finalization",
        )

    alanya_campaign.refresh_from_db()
    before_retry = (
        alanya_campaign.raw_records_found,
        alanya_campaign.normalized_records,
        alanya_campaign.completed_jobs,
        alanya_campaign.failed_jobs,
    )
    assert before_retry == (6, 6, 2, 0)
    assert (
        NormalizedSourceRecord.objects.filter(source_record__campaign=alanya_campaign).count() == 6
    )

    replay_finished = Event()
    replay_task_id = str(uuid4())
    replay_states: list[str | None] = []

    def mark_replay_finished(*, task_id=None, state=None, **kwargs) -> None:
        if task_id == replay_task_id:
            replay_states.append(state)
            replay_finished.set()

    task_postrun.connect(mark_replay_finished, weak=False)
    try:
        with start_worker(
            celery_app,
            queues=["discovery"],
            pool="solo",
            concurrency=1,
            perform_ping_check=False,
        ):
            run_discovery_campaign.apply_async(
                args=[str(alanya_campaign.id)],
                task_id=replay_task_id,
            )
            assert replay_finished.wait(timeout=10)
    finally:
        task_postrun.disconnect(mark_replay_finished)

    assert replay_states == ["SUCCESS"]
    alanya_campaign.refresh_from_db()
    assert (
        alanya_campaign.raw_records_found,
        alanya_campaign.normalized_records,
        alanya_campaign.completed_jobs,
        alanya_campaign.failed_jobs,
    ) == before_retry
    assert SourceRecord.objects.filter(campaign=alanya_campaign).count() == 6
    assert (
        NormalizedSourceRecord.objects.filter(source_record__campaign=alanya_campaign).count() == 6
    )
