import uuid
from decimal import Decimal
from typing import ClassVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.geography.models import SearchArea
from apps.sources.models import Source
from apps.taxonomy.models import BusinessCategory
from common.models import TimestampedUUIDModel


class DiscoveryCampaign(TimestampedUUIDModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        COMPLETED_WITH_ERRORS = "completed_with_errors", "Completed with errors"
        FAILED = "failed", "Failed"

    name = models.CharField(max_length=255)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="discovery_campaigns",
    )
    search_area = models.ForeignKey(
        SearchArea,
        on_delete=models.PROTECT,
        related_name="campaigns",
    )
    sources = models.ManyToManyField(
        Source,
        through="CampaignSource",
        related_name="campaigns",
    )
    categories = models.ManyToManyField(
        BusinessCategory,
        through="CampaignCategory",
        related_name="campaigns",
    )
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.DRAFT)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    total_jobs = models.PositiveBigIntegerField(default=0)
    completed_jobs = models.PositiveBigIntegerField(default=0)
    failed_jobs = models.PositiveBigIntegerField(default=0)
    raw_records_found = models.PositiveBigIntegerField(default=0)
    normalized_records = models.PositiveBigIntegerField(default=0)
    rejected_records = models.PositiveBigIntegerField(default=0)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=models.Q(
                    total_jobs__gte=models.F("completed_jobs") + models.F("failed_jobs")
                ),
                name="campaign_finished_jobs_lte_total",
            )
        ]

    def __str__(self) -> str:
        return self.name


class CampaignSource(TimestampedUUIDModel):
    campaign = models.ForeignKey(
        DiscoveryCampaign,
        on_delete=models.CASCADE,
        related_name="source_selections",
    )
    source = models.ForeignKey(
        Source,
        on_delete=models.PROTECT,
        related_name="campaign_selections",
    )
    is_enabled = models.BooleanField(default=True)
    priority = models.PositiveSmallIntegerField(default=100)
    request_limit = models.PositiveBigIntegerField(null=True, blank=True)
    budget_limit = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal(0))],
    )

    class Meta:
        ordering = ("priority", "created_at", "id")
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=("campaign", "source"),
                name="campaign_source_uniq",
            )
        ]

    def __str__(self) -> str:
        return f"{self.campaign.name}: {self.source.code}"

    def clean(self) -> None:
        super().clean()
        if (
            self.source_id
            and not self.source.is_paid
            and self.budget_limit is not None
            and self.budget_limit != 0
        ):
            raise ValidationError(
                {"budget_limit": "Для бесплатного источника нельзя задавать ненулевой бюджет."}
            )


class CampaignCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(
        DiscoveryCampaign,
        on_delete=models.CASCADE,
        related_name="category_selections",
    )
    category = models.ForeignKey(
        BusinessCategory,
        on_delete=models.PROTECT,
        related_name="campaign_selections",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "id")
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=("campaign", "category"),
                name="campaign_category_uniq",
            )
        ]

    def __str__(self) -> str:
        return f"{self.campaign.name}: {self.category.name}"


class CampaignSourceRun(TimestampedUUIDModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        NORMALIZING = "normalizing", "Normalizing"
        COMPLETED = "completed", "Completed"
        COMPLETED_WITH_ERRORS = "completed_with_errors", "Completed with errors"
        FAILED = "failed", "Failed"

    campaign = models.ForeignKey(
        DiscoveryCampaign,
        on_delete=models.CASCADE,
        related_name="source_runs",
    )
    source = models.ForeignKey(
        Source,
        on_delete=models.PROTECT,
        related_name="campaign_runs",
    )
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)
    source_dataset_version = models.CharField(max_length=255, null=True, blank=True)
    discovered_records = models.PositiveBigIntegerField(default=0)
    stored_records = models.PositiveBigIntegerField(default=0)
    normalized_records = models.PositiveBigIntegerField(default=0)
    rejected_records = models.PositiveBigIntegerField(default=0)
    failed_records = models.PositiveBigIntegerField(default=0)
    request_count = models.PositiveBigIntegerField(default=0)
    source_retry_count = models.PositiveSmallIntegerField(default=0)
    cost = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal(0))
    started_at = models.DateTimeField(null=True, blank=True)
    discovery_finished_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=64, null=True, blank=True)
    error_detail = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ("created_at", "id")
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=("campaign", "source"),
                name="campaign_source_run_uniq",
            )
        ]

    def __str__(self) -> str:
        return f"{self.campaign.name}: {self.source.code} ({self.status})"


class PipelineRetryReservation(TimestampedUUIDModel):
    class Scope(models.TextChoices):
        SOURCE_DISCOVERY = "source_discovery", "Source discovery"
        SOURCE_NORMALIZATION = "source_normalization", "Source normalization"

    campaign = models.ForeignKey(
        DiscoveryCampaign,
        on_delete=models.CASCADE,
        related_name="retry_reservations",
    )
    scope = models.CharField(max_length=32, choices=Scope.choices)
    work_id = models.UUIDField()
    delivery_token = models.CharField(max_length=128)
    allowed = models.BooleanField()

    class Meta:
        ordering = ("created_at", "id")
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=("scope", "work_id", "delivery_token"),
                name="uniq_pipeline_retry_delivery",
            ),
            models.CheckConstraint(
                condition=models.Q(scope__in=("source_discovery", "source_normalization")),
                name="pipeline_retry_scope_valid",
            ),
        ]
        indexes: ClassVar = [
            models.Index(
                fields=("campaign", "scope", "created_at"),
                name="pipeline_retry_campaign_scope",
            )
        ]
