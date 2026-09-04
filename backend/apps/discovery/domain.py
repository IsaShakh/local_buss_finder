from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

type JSONScalar = str | int | float | bool | None
type JSONValue = JSONScalar | list[JSONValue] | dict[str, JSONValue]


@dataclass(frozen=True)
class BoundingBox:
    west: float
    south: float
    east: float
    north: float

    def __post_init__(self) -> None:
        if not (-180 <= self.west <= 180 and -180 <= self.east <= 180):
            raise ValueError("west and east must be valid WGS84 longitudes")
        if not (-90 <= self.south <= 90 and -90 <= self.north <= 90):
            raise ValueError("south and north must be valid WGS84 latitudes")
        if self.west >= self.east:
            raise ValueError("west must be less than east")
        if self.south >= self.north:
            raise ValueError("south must be less than north")


@dataclass(frozen=True)
class DiscoveryRequest:
    campaign_id: UUID
    source_run_id: UUID
    search_area_id: UUID
    dataset_version: str
    bbox: BoundingBox
    geometry_geojson: dict[str, JSONValue]
    external_categories: tuple[str, ...]
    result_limit: int | None
    correlation_id: str

    def __post_init__(self) -> None:
        if not self.dataset_version.strip():
            raise ValueError("dataset_version must not be empty")
        if not self.correlation_id.strip():
            raise ValueError("correlation_id must not be empty")
        if not self.external_categories:
            raise ValueError("external_categories must not be empty")
        if self.result_limit is not None and self.result_limit <= 0:
            raise ValueError("result_limit must be positive when provided")


@dataclass(frozen=True)
class SourceProvenance:
    dataset_version: str
    source_url: str | None
    attribution: str
    license_code: str


@dataclass(frozen=True)
class SourcePayload:
    external_id: str
    payload: dict[str, JSONValue]
    fetched_at: datetime
    provenance: SourceProvenance


@dataclass(frozen=True)
class RawBusinessRecord:
    external_id: str
    raw_name: str | None
    raw_category: str | None
    raw_address: str | None
    raw_phones: tuple[str, ...]
    raw_emails: tuple[str, ...]
    raw_websites: tuple[str, ...]
    raw_social_urls: dict[str, tuple[str, ...]]
    longitude: float | None
    latitude: float | None


class DiscoveryAdapter(Protocol):
    source_code: str

    def resolve_dataset_version(self) -> str: ...

    def discover(self, request: DiscoveryRequest) -> Iterator[SourcePayload]: ...

    def parse_payload(self, source_payload: SourcePayload) -> RawBusinessRecord: ...
