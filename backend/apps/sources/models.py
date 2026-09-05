from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any, ClassVar

from django.contrib.gis.db import models as gis_models
from django.contrib.postgres.indexes import GistIndex
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from common.models import TimestampedUUIDModel

SECRET_KEY_FRAGMENTS = ("secret", "token", "password", "api_key")


def _find_secret_like_keys(value: Any, *, path: str = "settings") -> list[str]:
    matches: list[str] = []

    if isinstance(value, Mapping):
        for key, nested_value in value.items():
            key_name = str(key)
            nested_path = f"{path}.{key_name}"
            normalized_key = key_name.casefold()
            if any(fragment in normalized_key for fragment in SECRET_KEY_FRAGMENTS):
                matches.append(nested_path)
            matches.extend(_find_secret_like_keys(nested_value, path=nested_path))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, nested_value in enumerate(value):
            matches.extend(_find_secret_like_keys(nested_value, path=f"{path}[{index}]"))

    return matches


class Source(TimestampedUUIDModel):
    class Type(models.TextChoices):
        OPEN_DATA = "open_data", "Open data"
        API = "api", "API"
        DIRECTORY = "directory", "Directory"
        WEBSITE = "website", "Website"
        MANUAL = "manual", "Manual"

    code = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    source_type = models.CharField(max_length=32, choices=Type.choices)
    attribution = models.TextField()
    license_code = models.CharField(max_length=255)
    is_paid = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    requests_per_second = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("1.00"),
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    concurrency = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
    )
    timeout_seconds = models.PositiveSmallIntegerField(
        default=60,
        validators=[MinValueValidator(1)],
    )
    max_retries = models.PositiveSmallIntegerField(default=3)
    settings = models.JSONField(default=dict, blank=True)
    request_count = models.PositiveBigIntegerField(default=0)
    total_cost = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=Decimal(0),
    )

    class Meta:
        ordering = ("code",)

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        forbidden_paths = _find_secret_like_keys(self.settings)
        if forbidden_paths:
            raise ValidationError(
                {
                    "settings": [
                        f"Секретные значения нельзя хранить в настройках: {path}."
                        for path in forbidden_paths
                    ]
                }
            )


class SourceRecord(TimestampedUUIDModel):
    class NormalizationStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        NORMALIZED = "normalized", "Normalized"
        REJECTED = "rejected", "Rejected"
        FAILED = "failed", "Failed"

    campaign = models.ForeignKey(
        "campaigns.DiscoveryCampaign",
        on_delete=models.CASCADE,
        related_name="source_records",
    )
    source_run = models.ForeignKey(
        "campaigns.CampaignSourceRun",
        on_delete=models.CASCADE,
        related_name="records",
    )
    source = models.ForeignKey(
        Source,
        on_delete=models.PROTECT,
        related_name="source_records",
    )
    external_id = models.CharField(max_length=512)
    source_dataset_version = models.CharField(max_length=255)
    source_url = models.TextField(null=True, blank=True)
    attribution = models.TextField()
    license_code = models.CharField(max_length=255)
    raw_name = models.TextField(null=True, blank=True)
    raw_category = models.TextField(null=True, blank=True)
    raw_address = models.TextField(null=True, blank=True)
    raw_phones = models.JSONField(default=list, blank=True)
    raw_emails = models.JSONField(default=list, blank=True)
    raw_websites = models.JSONField(default=list, blank=True)
    raw_social_urls = models.JSONField(default=dict, blank=True)
    raw_location = gis_models.PointField(srid=4326, null=True, blank=True)
    raw_payload_key = models.TextField()
    raw_payload_sha256 = models.CharField(max_length=64)
    raw_payload_bytes = models.PositiveBigIntegerField()
    payload_schema_version = models.CharField(max_length=32)
    checksum = models.CharField(max_length=64)
    normalization_status = models.CharField(
        max_length=16,
        choices=NormalizationStatus.choices,
        default=NormalizationStatus.PENDING,
    )
    normalization_retry_count = models.PositiveSmallIntegerField(default=0)
    normalization_error_code = models.CharField(max_length=64, null=True, blank=True)
    parser_error_code = models.CharField(max_length=64, null=True, blank=True)
    fetched_at = models.DateTimeField()

    class Meta:
        ordering = ("-fetched_at", "-id")
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=("campaign", "source", "external_id"),
                name="uniq_campaign_source_external",
            )
        ]
        indexes: ClassVar = [
            models.Index(
                fields=("campaign", "normalization_status"),
                name="src_rec_campaign_status",
            ),
            models.Index(
                fields=("source", "external_id"),
                name="src_rec_source_external",
            ),
            models.Index(fields=("fetched_at",), name="src_rec_fetched_at"),
            GistIndex(fields=("raw_location",), name="src_rec_location_gist"),
        ]

    def __str__(self) -> str:
        return f"{self.source.code}: {self.external_id}"


class SourceRecordConflict(TimestampedUUIDModel):
    campaign = models.ForeignKey(
        "campaigns.DiscoveryCampaign",
        on_delete=models.CASCADE,
        related_name="source_record_conflicts",
    )
    source_run = models.ForeignKey(
        "campaigns.CampaignSourceRun",
        on_delete=models.CASCADE,
        related_name="record_conflicts",
    )
    source = models.ForeignKey(
        Source,
        on_delete=models.PROTECT,
        related_name="source_record_conflicts",
    )
    external_id = models.CharField(max_length=512)
    original_source_record = models.ForeignKey(
        SourceRecord,
        on_delete=models.CASCADE,
        related_name="conflicts",
    )
    conflicting_payload_sha256 = models.CharField(max_length=64)
    raw_payload_key = models.TextField()
    raw_payload_bytes = models.PositiveBigIntegerField()
    payload_schema_version = models.CharField(max_length=32)
    source_dataset_version = models.CharField(max_length=255)
    error_code = models.CharField(max_length=64, default="SOURCE_RECORD_CONFLICT")
    counted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("created_at", "id")
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=("campaign", "source", "external_id", "conflicting_payload_sha256"),
                name="uniq_campaign_source_external_conflict_sha",
            )
        ]

    def __str__(self) -> str:
        return f"{self.source.code}: {self.external_id} conflict"


class NormalizedSourceRecord(TimestampedUUIDModel):
    source_record = models.OneToOneField(
        SourceRecord,
        on_delete=models.CASCADE,
        related_name="normalized_record",
    )
    display_name = models.TextField()
    normalized_name = models.TextField()
    match_name = models.TextField()
    category = models.ForeignKey(
        "taxonomy.BusinessCategory",
        on_delete=models.PROTECT,
        related_name="normalized_source_records",
        null=True,
        blank=True,
    )
    address_text = models.TextField(blank=True)
    country = models.ForeignKey(
        "geography.Country",
        on_delete=models.PROTECT,
        related_name="normalized_source_records",
        null=True,
        blank=True,
    )
    province = models.ForeignKey(
        "geography.Province",
        on_delete=models.PROTECT,
        related_name="normalized_source_records",
        null=True,
        blank=True,
    )
    district = models.ForeignKey(
        "geography.District",
        on_delete=models.PROTECT,
        related_name="normalized_source_records",
        null=True,
        blank=True,
    )
    neighborhood = models.ForeignKey(
        "geography.Neighborhood",
        on_delete=models.PROTECT,
        related_name="normalized_source_records",
        null=True,
        blank=True,
    )
    location = gis_models.PointField(srid=4326, null=True, blank=True)
    phones = models.JSONField(default=list, blank=True)
    emails = models.JSONField(default=list, blank=True)
    websites = models.JSONField(default=list, blank=True)
    social_urls = models.JSONField(default=dict, blank=True)
    attributes = models.JSONField(default=dict, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    normalization_version = models.CharField(max_length=32)
    normalized_at = models.DateTimeField()

    class Meta:
        ordering = ("-normalized_at", "-id")
        indexes: ClassVar = [
            GistIndex(fields=("location",), name="norm_src_location_gist"),
        ]

    def __str__(self) -> str:
        return self.display_name
