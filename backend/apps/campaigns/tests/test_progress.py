from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.campaigns.models import CampaignSourceRun, DiscoveryCampaign
from apps.campaigns.progress import (
    finalize_source_run,
    get_campaign_progress,
    try_finalize_campaign,
)


@pytest.fixture
def campaign_with_ready_runs(alanya_campaign):
    def create(*, statuses, counters=((0, 0, 0, 0), (0, 0, 0, 0))):
        campaign = alanya_campaign
        campaign.status = DiscoveryCampaign.Status.RUNNING
        campaign.total_jobs = 2
        campaign.save(update_fields=("status", "total_jobs", "updated_at"))
        runs = []
        for source, values in zip(campaign.sources.order_by("code"), counters, strict=True):
            stored, normalized, rejected, failed = values
            run = CampaignSourceRun.objects.create(
                campaign=campaign,
                source=source,
                status=CampaignSourceRun.Status.NORMALIZING,
                source_dataset_version=f"fixture-{source.code}",
                discovered_records=stored,
                stored_records=stored,
                normalized_records=normalized,
                rejected_records=rejected,
                failed_records=failed,
                discovery_finished_at=timezone.now(),
            )
            runs.append(run)
        for run, status in zip(runs, statuses, strict=True):
            finalize_source_run(source_run_id=run.id, status=status)
        campaign.refresh_from_db()
        return campaign

    return create


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (("completed", "completed"), "completed"),
        (("failed", "completed"), "completed_with_errors"),
        (("failed", "failed"), "failed"),
    ],
)
def test_campaign_terminal_status_matrix(campaign_with_ready_runs, statuses, expected):
    campaign = campaign_with_ready_runs(statuses=statuses)

    assert try_finalize_campaign(campaign.id) == expected
    campaign.refresh_from_db()
    assert campaign.status == expected


@pytest.mark.django_db(transaction=True)
def test_rejected_record_is_processed_but_not_failed(campaign_with_ready_runs):
    campaign = campaign_with_ready_runs(
        statuses=("completed", "completed"),
        counters=((1, 0, 1, 0), (0, 0, 0, 0)),
    )
    run = campaign.source_runs.order_by("source__code").first()

    assert run.normalized_records + run.rejected_records + run.failed_records == (
        run.stored_records
    )
    assert run.failed_records == 0
    assert try_finalize_campaign(campaign.id) == "completed"


@pytest.mark.django_db
def test_progress_aggregates_persisted_campaign_and_source_counters(
    ready_run_with_one_pending_record,
    owner,
):
    run = ready_run_with_one_pending_record
    progress = get_campaign_progress(run.campaign_id, actor=owner)

    assert progress.id == run.campaign_id
    assert progress.status == "running"
    assert progress.totals.jobs == 1
    assert progress.totals.discovered == 1
    assert progress.totals.stored == 1
    assert progress.totals.normalized == 0
    assert len(progress.sources) == 1
    assert progress.sources[0].code == "osm"
    assert progress.sources[0].status == "normalizing"
    assert progress.sources[0].dataset_version == "fixture-2026-09"


@pytest.mark.django_db
def test_progress_query_count_is_constant(
    ready_run_with_one_pending_record,
    owner,
    django_assert_num_queries,
):
    with django_assert_num_queries(2):
        progress = get_campaign_progress(
            ready_run_with_one_pending_record.campaign_id,
            actor=owner,
        )

    assert len(progress.sources) == 1


@pytest.mark.django_db
def test_progress_api_returns_exact_contract(auth_client, ready_run_with_one_pending_record):
    run = ready_run_with_one_pending_record

    response = auth_client.get(f"/api/v1/campaigns/{run.campaign_id}/progress/")

    assert response.status_code == 200
    assert response.json() == {
        "id": str(run.campaign_id),
        "status": "running",
        "totals": {
            "jobs": 1,
            "completed_jobs": 0,
            "failed_jobs": 0,
            "discovered": 1,
            "stored": 1,
            "normalized": 0,
            "rejected": 0,
            "failed_records": 0,
        },
        "sources": [
            {
                "code": "osm",
                "name": "OpenStreetMap",
                "status": "normalizing",
                "dataset_version": "fixture-2026-09",
                "discovered": 1,
                "stored": 1,
                "normalized": 0,
                "rejected": 0,
                "failed_records": 0,
            }
        ],
    }


@pytest.mark.django_db
def test_progress_api_hides_other_owners_campaign(
    api_client,
    other_owner,
    ready_run_with_one_pending_record,
):
    api_client.force_authenticate(other_owner)

    response = api_client.get(
        f"/api/v1/campaigns/{ready_run_with_one_pending_record.campaign_id}/progress/"
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.django_db(transaction=True)
def test_repeated_terminal_transition_recovers_campaign_finalization(
    ready_run_with_one_pending_record,
):
    run = ready_run_with_one_pending_record
    record = run.records.get()
    record.normalization_status = "normalized"
    record.save(update_fields=("normalization_status", "updated_at"))
    run.normalized_records = 1
    run.save(update_fields=("normalized_records", "updated_at"))

    with patch("apps.campaigns.progress.transaction.on_commit"):
        assert finalize_source_run(source_run_id=run.id, status="completed") == "completed"
    run.campaign.refresh_from_db()
    assert run.campaign.status == "running"

    assert finalize_source_run(source_run_id=run.id, status="completed") == "completed"
    run.campaign.refresh_from_db()
    assert run.campaign.status == "completed"
