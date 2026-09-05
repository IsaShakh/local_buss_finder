from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Literal

from apps.discovery.domain import (
    DiscoveryRequest,
    JSONValue,
    RawBusinessRecord,
    SourcePayload,
    SourceProvenance,
)

FIXTURE_ATTRIBUTION = {
    "overture": "Overture Maps Foundation (fixture)",
    "osm": "© OpenStreetMap contributors (fixture)",
}
FIXTURE_LICENSE = {
    "overture": "fixture-only-overture",
    "osm": "fixture-only-osm",
}
FIXTURE_PAYLOADS: dict[str, tuple[dict[str, JSONValue], ...]] = {
    "overture": (
        {
            "id": "fixture-overture-1",
            "name": "Alanya Overture Dental",
            "category": "dentist",
            "address": "Saray, Alanya",
            "longitude": 32.01,
            "latitude": 36.55,
        },
        {
            "id": "fixture-shared",
            "name": "Shared Alanya Dental",
            "category": "dentist",
            "address": "Saray, Alanya",
            "longitude": 32.02,
            "latitude": 36.56,
        },
    ),
    "osm": (
        {
            "id": "fixture-osm-1",
            "name": "Alanya OSM Dental",
            "category": "amenity=dentist",
            "address": "Saray, Alanya",
            "longitude": 32.03,
            "latitude": 36.57,
        },
        {
            "id": "fixture-shared",
            "name": "Shared Alanya Dental",
            "category": "amenity=dentist",
            "address": "Saray, Alanya",
            "longitude": 32.02,
            "latitude": 36.56,
        },
    ),
}


def _text(payload: dict[str, JSONValue], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) and value else None


def _coordinate(payload: dict[str, JSONValue], key: str) -> float | None:
    value = payload.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def parse_fixture_payload(source_payload: SourcePayload) -> RawBusinessRecord:
    payload = source_payload.payload
    return RawBusinessRecord(
        external_id=source_payload.external_id,
        raw_name=_text(payload, "name"),
        raw_category=_text(payload, "category"),
        raw_address=_text(payload, "address"),
        raw_phones=(),
        raw_emails=(),
        raw_websites=(),
        raw_social_urls={},
        longitude=_coordinate(payload, "longitude"),
        latitude=_coordinate(payload, "latitude"),
    )


class FixtureDiscoveryAdapter:
    def __init__(self, source_code: Literal["overture", "osm"]) -> None:
        self.source_code = source_code

    def resolve_dataset_version(self) -> str:
        return "fixture-2026-09"

    def discover(self, request: DiscoveryRequest) -> Iterator[SourcePayload]:
        for payload in FIXTURE_PAYLOADS[self.source_code]:
            external_id = _text(payload, "id")
            category = _text(payload, "category")
            if external_id is None or category not in request.external_categories:
                continue
            yield SourcePayload(
                external_id=external_id,
                payload=payload,
                fetched_at=datetime(2026, 9, 4, tzinfo=UTC),
                provenance=SourceProvenance(
                    dataset_version=request.dataset_version,
                    source_url=None,
                    attribution=FIXTURE_ATTRIBUTION[self.source_code],
                    license_code=FIXTURE_LICENSE[self.source_code],
                ),
            )

    def parse_payload(self, source_payload: SourcePayload) -> RawBusinessRecord:
        return parse_fixture_payload(source_payload)


class FixtureOvertureAdapter(FixtureDiscoveryAdapter):
    def __init__(self) -> None:
        super().__init__("overture")


class FixtureOsmAdapter(FixtureDiscoveryAdapter):
    def __init__(self) -> None:
        super().__init__("osm")
