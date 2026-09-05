from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone

from apps.campaigns.models import CampaignSourceRun, DiscoveryCampaign

type TerminalRunStatus = Literal["completed", "completed_with_errors", "failed"]

TERMINAL_RUN_STATUSES = {
    CampaignSourceRun.Status.COMPLETED,
    CampaignSourceRun.Status.COMPLETED_WITH_ERRORS,
    CampaignSourceRun.Status.FAILED,
}
TERMINAL_CAMPAIGN_STATUSES = {
    DiscoveryCampaign.Status.COMPLETED,
    DiscoveryCampaign.Status.COMPLETED_WITH_ERRORS,
    DiscoveryCampaign.Status.FAILED,
}


@dataclass(frozen=True)
class CampaignTotals:
    jobs: int
    completed_jobs: int
    failed_jobs: int
    discovered: int
    stored: int
    normalized: int
    rejected: int
    failed_records: int


@dataclass(frozen=True)
class SourceProgress:
    code: str
    name: str
    status: str
    dataset_version: str | None
    discovered: int
    stored: int
    normalized: int
    rejected: int
    failed_records: int


@dataclass(frozen=True)
class CampaignProgress:
    id: UUID
    status: str
    totals: CampaignTotals
    sources: tuple[SourceProgress, ...]


def _run_is_ready(run: CampaignSourceRun) -> bool:
    processed = run.normalized_records + run.rejected_records + run.failed_records
    return run.discovery_finished_at is not None and processed == run.stored_records


def try_finalize_campaign(campaign_id: UUID) -> DiscoveryCampaign.Status:
    with transaction.atomic():
        campaign = DiscoveryCampaign.objects.select_for_update().get(id=campaign_id)
        if campaign.status in TERMINAL_CAMPAIGN_STATUSES:
            return campaign.status
        runs = list(campaign.source_runs.all())
        if not runs or not all(
            _run_is_ready(run) and run.status in TERMINAL_RUN_STATUSES for run in runs
        ):
            return campaign.status

        statuses = {run.status for run in runs}
        if statuses == {CampaignSourceRun.Status.FAILED}:
            status = DiscoveryCampaign.Status.FAILED
        elif statuses.intersection(
            {
                CampaignSourceRun.Status.FAILED,
                CampaignSourceRun.Status.COMPLETED_WITH_ERRORS,
            }
        ):
            status = DiscoveryCampaign.Status.COMPLETED_WITH_ERRORS
        else:
            status = DiscoveryCampaign.Status.COMPLETED
        campaign.status = status
        campaign.finished_at = timezone.now()
        campaign.save(update_fields=("status", "finished_at", "updated_at"))
        return campaign.status


def finalize_source_run(
    *,
    source_run_id: UUID,
    status: TerminalRunStatus,
    error_code: str | None = None,
    error_detail: str = "",
) -> CampaignSourceRun.Status:
    with transaction.atomic():
        campaign_id = CampaignSourceRun.objects.values_list("campaign_id", flat=True).get(
            id=source_run_id
        )
        campaign = DiscoveryCampaign.objects.select_for_update().get(id=campaign_id)
        source_run = CampaignSourceRun.objects.select_for_update().get(id=source_run_id)
        if source_run.status in TERMINAL_RUN_STATUSES:
            transaction.on_commit(lambda: try_finalize_campaign(campaign.id))
            return source_run.status
        if not _run_is_ready(source_run):
            return source_run.status

        final_status = status
        if status == CampaignSourceRun.Status.COMPLETED and (
            source_run.failed_records > 0 or source_run.error_code
        ):
            final_status = CampaignSourceRun.Status.COMPLETED_WITH_ERRORS
        source_run.status = final_status
        source_run.error_code = error_code or source_run.error_code
        source_run.error_detail = error_detail or source_run.error_detail
        source_run.finished_at = timezone.now()
        source_run.save(
            update_fields=(
                "status",
                "error_code",
                "error_detail",
                "finished_at",
                "updated_at",
            )
        )
        if final_status == CampaignSourceRun.Status.FAILED:
            campaign.failed_jobs += 1
            fields = ("failed_jobs", "updated_at")
        else:
            campaign.completed_jobs += 1
            fields = ("completed_jobs", "updated_at")
        campaign.save(update_fields=fields)
        transaction.on_commit(lambda: try_finalize_campaign(campaign.id))
        return source_run.status


def get_campaign_progress(
    campaign_id: UUID,
    actor: AbstractBaseUser,
) -> CampaignProgress:
    campaign = (
        DiscoveryCampaign.objects.filter(id=campaign_id, created_by_id=actor.pk)
        .prefetch_related(
            Prefetch(
                "source_runs",
                queryset=CampaignSourceRun.objects.select_related("source"),
            )
        )
        .get()
    )
    runs = tuple(campaign.source_runs.all())
    return CampaignProgress(
        id=campaign.id,
        status=campaign.status,
        totals=CampaignTotals(
            jobs=campaign.total_jobs,
            completed_jobs=campaign.completed_jobs,
            failed_jobs=campaign.failed_jobs,
            discovered=sum(run.discovered_records for run in runs),
            stored=sum(run.stored_records for run in runs),
            normalized=sum(run.normalized_records for run in runs),
            rejected=sum(run.rejected_records for run in runs),
            failed_records=sum(run.failed_records for run in runs),
        ),
        sources=tuple(
            SourceProgress(
                code=run.source.code,
                name=run.source.name,
                status=run.status,
                dataset_version=run.source_dataset_version,
                discovered=run.discovered_records,
                stored=run.stored_records,
                normalized=run.normalized_records,
                rejected=run.rejected_records,
                failed_records=run.failed_records,
            )
            for run in runs
        ),
    )
