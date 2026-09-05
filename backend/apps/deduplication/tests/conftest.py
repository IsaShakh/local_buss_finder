from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from django.contrib.gis.geos import MultiPolygon, Point, Polygon


@pytest.fixture
def normalized_record_factory(owner) -> Callable[..., object]:
    """Create normalized records directly, without running discovery adapters."""
    from apps.campaigns.models import CampaignSource, CampaignSourceRun, DiscoveryCampaign
    from apps.geography.models import Country, District, Neighborhood, Province, SearchArea
    from apps.sources.models import NormalizedSourceRecord, Source, SourceRecord

    suffix = uuid4().hex[:8]
    country = Country.objects.create(code="TR", name=f"Turkey {suffix}", name_ru=f"Турция {suffix}")
    province = Province.objects.create(
        country=country,
        code=f"fixture-{suffix}",
        name=f"Province {suffix}",
        name_ru=f"Провинция {suffix}",
    )
    district = District.objects.create(
        province=province,
        slug=f"district-{suffix}",
        name=f"District {suffix}",
        name_ru=f"Район {suffix}",
    )
    neighborhood = Neighborhood.objects.create(
        district=district,
        slug=f"neighborhood-{suffix}",
        name=f"Neighborhood {suffix}",
        name_ru=f"Микрорайон {suffix}",
    )
    search_area = SearchArea.objects.create(
        name=f"Area {suffix}",
        country=country,
        province=province,
        district=district,
        neighborhood=neighborhood,
        geometry=MultiPolygon(
            Polygon(((32.0, 36.0), (32.1, 36.0), (32.1, 36.1), (32.0, 36.0)), srid=4326)
        ),
    )
    serial = 0
    sources: dict[str, Source] = {}

    def create(
        *,
        source_code: str,
        fetched_at: datetime = datetime(2026, 9, 5, tzinfo=UTC),
        normalized_id: UUID | None = None,
        display_name: str = "Alanya Smile",
        normalized_name: str = "alanya smile",
        match_name: str = "alanya smile",
        category=None,
        address_text: str = "Saray, Alanya",
        country_value=None,
        province_value=None,
        district_value=None,
        neighborhood_value=None,
        location=None,
        phones: list[str] | None = None,
        emails: list[str] | None = None,
        websites: list[str] | None = None,
        social_urls: dict[str, list[str]] | None = None,
    ):
        nonlocal serial
        serial += 1
        source = sources.get(source_code)
        if source is None:
            source = Source.objects.create(
                code=f"{source_code}-{suffix}",
                name=source_code,
                source_type=Source.Type.DIRECTORY,
                attribution="fixture",
                license_code="fixture-only",
            )
            sources[source_code] = source
        campaign = DiscoveryCampaign.objects.create(
            name=f"Campaign {serial} {suffix}",
            created_by=owner,
            search_area=search_area,
        )
        CampaignSource.objects.create(campaign=campaign, source=source)
        source_run = CampaignSourceRun.objects.create(campaign=campaign, source=source)
        source_record = SourceRecord.objects.create(
            campaign=campaign,
            source_run=source_run,
            source=source,
            external_id=f"fixture-{serial}",
            source_dataset_version="fixture-v1",
            source_url=f"https://{source_code}.example.test/{serial}",
            attribution="fixture",
            license_code="fixture-only",
            raw_payload_key=f"raw/{suffix}/{serial}.json.gz",
            raw_payload_sha256=f"{serial:064x}",
            raw_payload_bytes=1,
            payload_schema_version="1",
            checksum=f"{serial + 100:064x}",
            fetched_at=fetched_at,
        )
        return NormalizedSourceRecord.objects.create(
            id=normalized_id or uuid4(),
            source_record=source_record,
            display_name=display_name,
            normalized_name=normalized_name,
            match_name=match_name,
            category=category,
            address_text=address_text,
            country=country if country_value is None else country_value,
            province=province if province_value is None else province_value,
            district=district if district_value is None else district_value,
            neighborhood=neighborhood if neighborhood_value is None else neighborhood_value,
            location=Point(32.5, 36.5, srid=4326) if location is None else location,
            phones=[] if phones is None else phones,
            emails=[] if emails is None else emails,
            websites=[] if websites is None else websites,
            social_urls={} if social_urls is None else social_urls,
            attributes={},
            warnings=[],
            normalization_version="fixture-v1",
            normalized_at=fetched_at,
        )

    return create
