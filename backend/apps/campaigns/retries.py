from uuid import UUID

from django.db import transaction

from apps.campaigns.models import (
    CampaignSourceRun,
    DiscoveryCampaign,
    PipelineRetryReservation,
)
from apps.sources.models import SourceRecord


def consume_source_retry(*, source_run_id: UUID, delivery_token: str) -> bool:
    with transaction.atomic():
        campaign_id = CampaignSourceRun.objects.values_list("campaign_id", flat=True).get(
            id=source_run_id
        )
        campaign = DiscoveryCampaign.objects.select_for_update().get(id=campaign_id)
        source_run = CampaignSourceRun.objects.select_for_update().get(id=source_run_id)
        existing = PipelineRetryReservation.objects.filter(
            scope=PipelineRetryReservation.Scope.SOURCE_DISCOVERY,
            work_id=source_run.id,
            delivery_token=delivery_token,
        ).first()
        if existing is not None:
            return existing.allowed

        allowed = source_run.source_retry_count < source_run.source.max_retries
        if allowed:
            source_run.source_retry_count += 1
            source_run.save(update_fields=("source_retry_count", "updated_at"))
        PipelineRetryReservation.objects.create(
            campaign=campaign,
            scope=PipelineRetryReservation.Scope.SOURCE_DISCOVERY,
            work_id=source_run.id,
            delivery_token=delivery_token,
            allowed=allowed,
        )
        return allowed


def consume_normalization_retry(*, source_record_id: UUID, delivery_token: str) -> bool:
    with transaction.atomic():
        references = SourceRecord.objects.values("campaign_id", "source_run_id").get(
            id=source_record_id
        )
        campaign = DiscoveryCampaign.objects.select_for_update().get(id=references["campaign_id"])
        CampaignSourceRun.objects.select_for_update().get(id=references["source_run_id"])
        source_record = SourceRecord.objects.select_for_update().get(id=source_record_id)
        existing = PipelineRetryReservation.objects.filter(
            scope=PipelineRetryReservation.Scope.SOURCE_NORMALIZATION,
            work_id=source_record.id,
            delivery_token=delivery_token,
        ).first()
        if existing is not None:
            return existing.allowed

        allowed = source_record.normalization_retry_count < source_record.source.max_retries
        if allowed:
            source_record.normalization_retry_count += 1
            source_record.save(update_fields=("normalization_retry_count", "updated_at"))
        PipelineRetryReservation.objects.create(
            campaign=campaign,
            scope=PipelineRetryReservation.Scope.SOURCE_NORMALIZATION,
            work_id=source_record.id,
            delivery_token=delivery_token,
            allowed=allowed,
        )
        return allowed
