from uuid import UUID

from celery import shared_task
from django.db import OperationalError, transaction

from apps.campaigns.models import CampaignSourceRun, DiscoveryCampaign
from apps.campaigns.progress import finalize_source_run
from apps.campaigns.retries import consume_normalization_retry
from apps.normalization.services import materialize_normalization
from apps.sources.models import SourceRecord
from apps.sources.storage import RawStorageUnavailable
from config.celery_retry import (
    database_backoff,
    make_delivery_token,
    provider_backoff,
    retry_or_requeue,
)


def _finalize_record_run(source_run_id: UUID) -> None:
    source_run = CampaignSourceRun.objects.get(id=source_run_id)
    processed = (
        source_run.normalized_records + source_run.rejected_records + source_run.failed_records
    )
    if source_run.discovery_finished_at is None or processed != source_run.stored_records:
        return
    status = (
        CampaignSourceRun.Status.COMPLETED_WITH_ERRORS
        if source_run.failed_records or source_run.error_code
        else CampaignSourceRun.Status.COMPLETED
    )
    finalize_source_run(source_run_id=source_run.id, status=status)


def normalize_source_record_now(source_record_id: UUID) -> None:
    source_run_id = SourceRecord.objects.values_list("source_run_id", flat=True).get(
        id=source_record_id
    )
    materialize_normalization(source_record_id)
    _finalize_record_run(source_run_id)


def fail_source_record_once(*, source_record_id: UUID, error_code: str) -> bool:
    with transaction.atomic():
        references = SourceRecord.objects.values("campaign_id", "source_run_id").get(
            id=source_record_id
        )
        DiscoveryCampaign.objects.select_for_update().get(id=references["campaign_id"])
        source_run = CampaignSourceRun.objects.select_for_update().get(
            id=references["source_run_id"]
        )
        source_record = SourceRecord.objects.select_for_update().get(id=source_record_id)
        if source_record.normalization_status != SourceRecord.NormalizationStatus.PENDING:
            return False
        source_record.normalization_status = SourceRecord.NormalizationStatus.FAILED
        source_record.normalization_error_code = error_code[:64]
        source_record.save(
            update_fields=("normalization_status", "normalization_error_code", "updated_at")
        )
        source_run.failed_records += 1
        source_run.save(update_fields=("failed_records", "updated_at"))
        transaction.on_commit(lambda: _finalize_record_run(source_run.id))
        return True


@shared_task(
    bind=True,
    max_retries=None,
    name="apps.normalization.tasks.normalize_source_record",
)
def normalize_source_record(self, source_record_id: str) -> None:
    source_record_uuid = UUID(source_record_id)
    try:
        try:
            normalize_source_record_now(source_record_uuid)
        except RawStorageUnavailable as error:
            delivery_token = make_delivery_token(
                task_id=self.request.id,
                retries=self.request.retries,
            )
            if consume_normalization_retry(
                source_record_id=source_record_uuid,
                delivery_token=delivery_token,
            ):
                retry_or_requeue(
                    self,
                    exc=error,
                    countdown=provider_backoff(retries=self.request.retries),
                )
            fail_source_record_once(
                source_record_id=source_record_uuid,
                error_code=error.code,
            )
    except OperationalError as error:
        retry_or_requeue(
            self,
            exc=error,
            countdown=database_backoff(retries=self.request.retries),
        )


__all__ = [
    "fail_source_record_once",
    "normalize_source_record",
    "normalize_source_record_now",
]
