from typing import ClassVar
from uuid import UUID

from django.conf import settings
from django.contrib.gis.db import models as gis_models
from django.contrib.postgres.indexes import GinIndex, GistIndex
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from common.models import TimestampedUUIDModel

RESOLUTION_VERSION = "deterministic-v1"


class ActiveBusinessManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(merged_into__isnull=True)


class Business(TimestampedUUIDModel):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="businesses",
    )
    primary_normalized_record = models.ForeignKey(
        "sources.NormalizedSourceRecord",
        on_delete=models.SET_NULL,
        related_name="primary_for_businesses",
        null=True,
        blank=True,
    )
    display_name = models.TextField(default="", blank=True)
    normalized_name = models.TextField(default="", blank=True)
    match_name = models.TextField(default="", blank=True)
    category = models.ForeignKey(
        "taxonomy.BusinessCategory",
        on_delete=models.PROTECT,
        related_name="businesses",
        null=True,
        blank=True,
    )
    address_text = models.TextField(default="", blank=True)
    country = models.ForeignKey(
        "geography.Country",
        on_delete=models.PROTECT,
        related_name="businesses",
        null=True,
        blank=True,
    )
    province = models.ForeignKey(
        "geography.Province",
        on_delete=models.PROTECT,
        related_name="businesses",
        null=True,
        blank=True,
    )
    district = models.ForeignKey(
        "geography.District",
        on_delete=models.PROTECT,
        related_name="businesses",
        null=True,
        blank=True,
    )
    neighborhood = models.ForeignKey(
        "geography.Neighborhood",
        on_delete=models.PROTECT,
        related_name="businesses",
        null=True,
        blank=True,
    )
    location = gis_models.PointField(srid=4326, null=True, blank=True, spatial_index=False)
    phones = models.JSONField(default=list, blank=True)
    emails = models.JSONField(default=list, blank=True)
    websites = models.JSONField(default=list, blank=True)
    domains = models.JSONField(default=list, blank=True)
    social_urls = models.JSONField(default=dict, blank=True)
    first_seen_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    resolution_version = models.CharField(max_length=32, default=RESOLUTION_VERSION)
    merged_into = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="merged_businesses",
        null=True,
        blank=True,
    )

    objects = models.Manager()
    active = ActiveBusinessManager()

    class Meta:
        ordering = ("display_name", "id")
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=~models.Q(id=models.F("merged_into_id")),
                name="business_not_self_merged",
            )
        ]
        indexes: ClassVar = [
            models.Index(fields=("owner", "merged_into"), name="business_owner_merged_idx"),
            models.Index(fields=("owner", "category"), name="business_owner_category_idx"),
            GistIndex(fields=("location",), name="business_location_gist"),
            GinIndex(
                fields=("match_name",),
                name="business_match_name_trgm",
                opclasses=("gin_trgm_ops",),
            ),
            GinIndex(fields=("phones",), name="business_phones_gin"),
            GinIndex(fields=("domains",), name="business_domains_gin"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.merged_into_id is None:
            return

        if self.merged_into_id == self.id:
            raise ValidationError({"merged_into": "A business cannot be its own merged target."})

        if self.owner_id and self.merged_into.owner_id != self.owner_id:
            raise ValidationError({"merged_into": "Merged businesses must have the same owner."})


class BusinessSourceMembership(TimestampedUUIDModel):
    class MatchKind(models.TextChoices):
        SEED = "seed", "Seed"
        SOURCE_IDENTITY = "source_identity", "Source identity"
        AUTOMATIC = "automatic", "Automatic"
        MANUAL = "manual", "Manual"

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    normalized_record = models.OneToOneField(
        "sources.NormalizedSourceRecord",
        on_delete=models.PROTECT,
        related_name="business_membership",
    )
    match_kind = models.CharField(
        max_length=32,
        choices=MatchKind.choices,
        default=MatchKind.SEED,
    )
    match_score = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    match_signals = models.JSONField(default=list, blank=True)
    resolution_version = models.CharField(max_length=32, default=RESOLUTION_VERSION)
    attached_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("attached_at", "id")
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=models.Q(match_score__gte=0) & models.Q(match_score__lte=100),
                name="business_membership_score_range",
            )
        ]


class DuplicateCandidate(TimestampedUUIDModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        REJECTED = "rejected", "Rejected"
        SUPERSEDED = "superseded", "Superseded"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="duplicate_candidates",
    )
    left_business = models.ForeignKey(
        Business,
        on_delete=models.PROTECT,
        related_name="left_duplicate_candidates",
    )
    right_business = models.ForeignKey(
        Business,
        on_delete=models.PROTECT,
        related_name="right_duplicate_candidates",
    )
    score = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    signals = models.JSONField(default=list, blank=True)
    resolution_version = models.CharField(max_length=32, default=RESOLUTION_VERSION)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="duplicate_decisions",
        null=True,
        blank=True,
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    survivor_business = models.ForeignKey(
        Business,
        on_delete=models.PROTECT,
        related_name="surviving_duplicate_candidates",
        null=True,
        blank=True,
    )
    merged_business = models.ForeignKey(
        Business,
        on_delete=models.PROTECT,
        related_name="merged_duplicate_candidates",
        null=True,
        blank=True,
    )
    moved_membership_ids = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ("-score", "created_at", "id")
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=("owner", "left_business", "right_business"),
                name="uniq_duplicate_candidate_owner_pair",
            ),
            models.CheckConstraint(
                condition=~models.Q(left_business=models.F("right_business")),
                name="duplicate_candidate_not_self_pair",
            ),
            models.CheckConstraint(
                condition=models.Q(score__gte=0) & models.Q(score__lte=100),
                name="duplicate_candidate_score_range",
            ),
        ]

    @staticmethod
    def ordered_pair(left_id: UUID, right_id: UUID) -> tuple[UUID, UUID]:
        return tuple(sorted((left_id, right_id), key=str))  # type: ignore[return-value]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}

        if self.left_business_id == self.right_business_id:
            errors["right_business"] = "A duplicate candidate must compare two businesses."

        for field_name, business in (
            ("left_business", self.left_business),
            ("right_business", self.right_business),
            ("survivor_business", self.survivor_business),
            ("merged_business", self.merged_business),
        ):
            if business is not None and self.owner_id and business.owner_id != self.owner_id:
                errors[field_name] = "Candidate businesses must have the same owner."

        if self.decided_by is not None and self.owner_id and self.decided_by_id != self.owner_id:
            errors["decided_by"] = "The decision actor must have the same owner."

        if errors:
            raise ValidationError(errors)
