from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

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
