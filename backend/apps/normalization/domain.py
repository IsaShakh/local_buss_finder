from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from apps.discovery.domain import JSONValue


@dataclass(frozen=True)
class GeoPoint:
    longitude: float
    latitude: float


@dataclass(frozen=True)
class NormalizedBusinessData:
    display_name: str
    normalized_name: str
    match_name: str
    category_id: UUID | None
    address_text: str
    location: GeoPoint | None
    phones: tuple[str, ...]
    emails: tuple[str, ...]
    websites: tuple[str, ...]
    social_urls: dict[str, tuple[str, ...]]
    warnings: tuple[str, ...]
    attributes: dict[str, JSONValue]


@dataclass(frozen=True)
class NormalizationResult:
    status: Literal["normalized", "rejected"]
    data: NormalizedBusinessData | None
    error_code: str | None


@dataclass(frozen=True)
class NormalizedStrings:
    values: tuple[str, ...]
    warnings: tuple[str, ...]
