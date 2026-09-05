from uuid import UUID

from celery import shared_task
from django.db import OperationalError

from apps.campaigns.models import CampaignSourceRun
from apps.campaigns.retries import consume_source_retry
from apps.discovery.errors import PermanentSourceError, RateLimitedSourceError, TransientSourceError
from apps.discovery.registry import get_adapter
from apps.discovery.services import (
    begin_campaign,
    mark_source_discovery_exhausted,
    run_source_discovery_now,
)
from apps.sources.storage import RawStorageUnavailable, build_raw_payload_store
from config.celery_retry import (
    database_backoff,
    make_delivery_token,
    provider_backoff,
    retry_or_requeue,
)


@shared_task(
    bind=True,
    max_retries=None,
    name="apps.discovery.tasks.run_discovery_campaign",
)
def run_discovery_campaign(self, campaign_id: str) -> None:
    try:
        source_run_ids = begin_campaign(UUID(campaign_id))
        for source_run_id in source_run_ids:
            run_source_discovery.delay(str(source_run_id))
    except OperationalError as error:
        retry_or_requeue(
            self,
            exc=error,
            countdown=database_backoff(retries=self.request.retries),
        )


@shared_task(
    bind=True,
    max_retries=None,
    name="apps.discovery.tasks.run_source_discovery",
)
def run_source_discovery(self, source_run_id: str) -> None:
    source_run_uuid = UUID(source_run_id)
    try:
        try:
            source_code = CampaignSourceRun.objects.values_list("source__code", flat=True).get(
                id=source_run_uuid
            )
            from apps.normalization.tasks import normalize_source_record

            run_source_discovery_now(
                source_run_id=source_run_uuid,
                adapter=get_adapter(source_code),
                store=build_raw_payload_store(),
                enqueue_normalization=lambda record_id: normalize_source_record.delay(
                    str(record_id)
                ),
            )
        except (TransientSourceError, RawStorageUnavailable) as error:
            delivery_token = make_delivery_token(
                task_id=self.request.id,
                retries=self.request.retries,
            )
            if consume_source_retry(
                source_run_id=source_run_uuid,
                delivery_token=delivery_token,
            ):
                retry_after = (
                    error.retry_after_seconds if isinstance(error, RateLimitedSourceError) else None
                )
                retry_or_requeue(
                    self,
                    exc=error,
                    countdown=provider_backoff(
                        retries=self.request.retries,
                        retry_after_seconds=retry_after,
                    ),
                )
            mark_source_discovery_exhausted(
                source_run_id=source_run_uuid,
                error_code=getattr(error, "code", "SOURCE_UNAVAILABLE"),
                error_detail=str(error),
            )
        except PermanentSourceError as error:
            mark_source_discovery_exhausted(
                source_run_id=source_run_uuid,
                error_code=error.code,
                error_detail=error.detail,
            )
    except OperationalError as error:
        retry_or_requeue(
            self,
            exc=error,
            countdown=database_backoff(retries=self.request.retries),
        )


__all__ = [
    "make_delivery_token",
    "run_discovery_campaign",
    "run_source_discovery",
]
