from collections.abc import Iterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from apps.discovery.domain import (
        DiscoveryRequest,
        RawBusinessRecord,
        SourcePayload,
    )


class FixtureDiscoveryAdapter:
    source_code = "fixture"

    def resolve_dataset_version(self) -> str:
        return "fixture-2026-09"

    def discover(self, request: "DiscoveryRequest") -> Iterator["SourcePayload"]:
        from apps.discovery.domain import SourcePayload, SourceProvenance

        yield SourcePayload(
            external_id="fixture/42",
            payload={"id": "fixture/42", "category": request.external_categories[0]},
            fetched_at=datetime(2026, 9, 4, 9, 30, tzinfo=UTC),
            provenance=SourceProvenance(
                dataset_version=request.dataset_version,
                source_url="https://fixture.test/places/42",
                attribution="Fixture data",
                license_code="TEST-1.0",
            ),
        )

    def parse_payload(self, source_payload: "SourcePayload") -> "RawBusinessRecord":
        from apps.discovery.domain import RawBusinessRecord

        return RawBusinessRecord(
            external_id=source_payload.external_id,
            raw_name="Alanya Fixture Dentist",
            raw_category="dentist",
            raw_address="Saray, Alanya",
            raw_phones=(),
            raw_emails=(),
            raw_websites=(),
            raw_social_urls={},
            longitude=32.0,
            latitude=36.55,
        )


def make_contract_adapter() -> FixtureDiscoveryAdapter:
    return FixtureDiscoveryAdapter()


def make_discovery_request(
    *, external_categories: tuple[str, ...] = ("dentist",)
) -> "DiscoveryRequest":
    from apps.discovery.domain import BoundingBox, DiscoveryRequest

    return DiscoveryRequest(
        campaign_id=UUID("00000000-0000-0000-0000-000000000001"),
        source_run_id=UUID("00000000-0000-0000-0000-000000000002"),
        search_area_id=UUID("00000000-0000-0000-0000-000000000003"),
        dataset_version="fixture-2026-09",
        bbox=BoundingBox(west=31.9, south=36.4, east=32.2, north=36.7),
        geometry_geojson={
            "type": "Polygon",
            "coordinates": [[[31.9, 36.4], [32.2, 36.4], [32.2, 36.7], [31.9, 36.4]]],
        },
        external_categories=external_categories,
        result_limit=100,
        correlation_id="fixture-correlation-id",
    )
