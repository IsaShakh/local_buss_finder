import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from apps.discovery.adapters.osm import OpenStreetMapAdapter, OverpassClient
from apps.discovery.domain import SourcePayload, SourceProvenance
from apps.discovery.errors import (
    InvalidSourcePayload,
    PermanentSourceError,
    RateLimitedSourceError,
    TransientSourceError,
)
from apps.discovery.registry import get_adapter
from apps.discovery.tests.contracts import assert_adapter_contract
from apps.discovery.tests.fakes import make_discovery_request

FIXTURE_DIR = Path(__file__).resolve().parents[3] / "tests/fixtures/sources/osm"
ENDPOINT = "https://overpass.acme.test/api/interpreter"
USER_AGENT = "local-business-intelligence/0.1 (+mailto:data@acme.io)"


@pytest.fixture
def osm_fixture():
    return json.loads((FIXTURE_DIR / "alanya_elements.json").read_text())


class RecordingOverpassClient:
    def __init__(self, response):
        self.response = response
        self.queries = []

    def fetch(self, query):
        self.queries.append(query)
        return self.response


def make_osm_payload(element):
    return SourcePayload(
        external_id=f"{element['type']}/{element['id']}",
        payload=element,
        fetched_at=datetime(2026, 9, 4, tzinfo=UTC),
        provenance=SourceProvenance(
            dataset_version="2026-08-snapshot",
            source_url=None,
            attribution="© OpenStreetMap contributors",
            license_code="ODbL-1.0",
        ),
    )


@pytest.fixture
def osm_adapter(osm_fixture):
    return OpenStreetMapAdapter(
        client=RecordingOverpassClient(osm_fixture),
        endpoint_url=ENDPOINT,
        dataset_version="2026-08-snapshot",
        timeout_seconds=60,
        max_size_bytes=268_435_456,
        clock=lambda: datetime(2026, 9, 4, 12, tzinfo=UTC),
    )


def test_osm_parser_uses_node_coordinates_and_way_center(osm_adapter, osm_fixture):
    records = [
        osm_adapter.parse_payload(make_osm_payload(element))
        for element in osm_fixture["elements"][:2]
    ]

    assert records[0].external_id == "node/101"
    assert (records[0].longitude, records[0].latitude) == (32.002, 36.545)
    assert records[1].external_id == "way/202"
    assert (records[1].longitude, records[1].latitude) == (32.01, 36.55)
    assert records[0].raw_category == "amenity=dentist"
    assert records[1].raw_category == "tourism=hotel"


def test_osm_parser_extracts_ordered_contacts_address_and_socials(osm_adapter, osm_fixture):
    record = osm_adapter.parse_payload(make_osm_payload(osm_fixture["elements"][0]))

    assert record.raw_name == "Alanya Test Diş Kliniği"
    assert record.raw_address == "Atatürk Caddesi, 12, Saray, Alanya, 07400"
    assert record.raw_phones == (
        "+90 242 000 00 01",
        "+90 242 000 00 02",
        "+90 242 999 00 00",
    )
    assert record.raw_emails == (
        "hello@alanya-dentist.example",
        "booking@alanya-dentist.example",
        "fallback@alanya-dentist.example",
    )
    assert record.raw_websites == (
        "https://contact.alanya-dentist.example/",
        "https://alanya-dentist.example/",
        "https://directory.alanya-dentist.example/",
    )
    assert record.raw_social_urls == {
        "facebook": ("https://facebook.com/alanya.test.dentist",),
        "instagram": ("https://instagram.com/alanya_test_dentist",),
        "twitter": ("https://twitter.com/alanya_dentist",),
        "x": ("https://x.com/alanya_dentist",),
    }


def test_osm_parser_uses_precedence_and_empty_values(osm_adapter):
    payload = make_osm_payload(
        {
            "type": "relation",
            "id": 303,
            "tags": {
                "office": "estate_agent",
                "tourism": "hotel",
                "shop": "beauty",
            },
        }
    )

    record = osm_adapter.parse_payload(payload)

    assert record.raw_category == "office=estate_agent"
    assert record.raw_name is None
    assert record.raw_address is None
    assert record.raw_phones == ()
    assert record.raw_emails == ()
    assert record.raw_websites == ()
    assert record.raw_social_urls == {}
    assert (record.longitude, record.latitude) == (None, None)


def test_overpass_client_posts_query_with_identity_and_timeout():
    with respx.mock(assert_all_called=True) as router:
        route = router.post(ENDPOINT).mock(return_value=httpx.Response(200, json={"elements": []}))
        result = OverpassClient(
            url=ENDPOINT,
            timeout_seconds=23,
            user_agent=USER_AGENT,
        ).fetch("[out:json];node(0,0,1,1);out;")

    assert result == {"elements": []}
    request = route.calls[0].request
    assert request.headers["User-Agent"] == USER_AGENT
    assert request.headers["Accept"] == "application/json"
    assert request.extensions["timeout"] == {
        "connect": 23,
        "read": 23,
        "write": 23,
        "pool": 23,
    }
    assert request.content == b"data=%5Bout%3Ajson%5D%3Bnode%280%2C0%2C1%2C1%29%3Bout%3B"


def test_overpass_client_classifies_rate_limit():
    with respx.mock:
        respx.post(ENDPOINT).mock(return_value=httpx.Response(429, headers={"Retry-After": "120"}))
        with pytest.raises(RateLimitedSourceError) as raised:
            OverpassClient(url=ENDPOINT, timeout_seconds=60, user_agent=USER_AGENT).fetch("query")

    assert raised.value.retry_after_seconds == 120


@pytest.mark.parametrize("status_code", [502, 503, 504])
def test_overpass_client_classifies_transient_gateway_errors(status_code):
    with respx.mock:
        respx.post(ENDPOINT).mock(return_value=httpx.Response(status_code))
        with pytest.raises(TransientSourceError):
            OverpassClient(url=ENDPOINT, timeout_seconds=60, user_agent=USER_AGENT).fetch("query")


def test_overpass_client_classifies_malformed_query_as_permanent():
    with respx.mock:
        respx.post(ENDPOINT).mock(return_value=httpx.Response(400, text="bad query"))
        with pytest.raises(PermanentSourceError):
            OverpassClient(url=ENDPOINT, timeout_seconds=60, user_agent=USER_AGENT).fetch("query")


@pytest.mark.parametrize(
    "response",
    [httpx.Response(200, text="not-json"), httpx.Response(200, json=["not-an-object"])],
)
def test_overpass_client_rejects_invalid_json_payload(response):
    with respx.mock:
        respx.post(ENDPOINT).mock(return_value=response)
        with pytest.raises(InvalidSourcePayload):
            OverpassClient(url=ENDPOINT, timeout_seconds=60, user_agent=USER_AGENT).fetch("query")


def test_osm_discover_builds_bounded_query_filters_and_limits_results(osm_fixture):
    response = {
        **osm_fixture,
        "elements": [
            {"type": "node", "id": 1, "tags": {"amenity": "cafe"}},
            *osm_fixture["elements"],
        ],
    }
    client = RecordingOverpassClient(response)
    adapter = OpenStreetMapAdapter(
        client=client,
        endpoint_url=ENDPOINT,
        dataset_version="2026-08-snapshot",
        timeout_seconds=45,
        max_size_bytes=1024,
    )
    request = replace(
        make_discovery_request(external_categories=("amenity=dentist", "tourism=hotel")),
        dataset_version="2026-08-snapshot",
        result_limit=2,
    )

    payloads = list(adapter.discover(request))

    assert [payload.external_id for payload in payloads] == ["node/101", "way/202"]
    assert client.queries == [
        (
            "[out:json][timeout:45][maxsize:1024];"
            '(nwr["amenity"="dentist"](36.4,31.9,36.7,32.2);'
            'nwr["tourism"="hotel"](36.4,31.9,36.7,32.2););'
            "out center tags;"
        )
    ]
    assert payloads[0].provenance == SourceProvenance(
        dataset_version="2026-08-snapshot",
        source_url=None,
        attribution="© OpenStreetMap contributors",
        license_code="ODbL-1.0",
    )


def test_osm_discover_rejects_schema_mismatch(osm_adapter):
    osm_adapter.client.response = {"elements": "not-a-list"}

    with pytest.raises(InvalidSourcePayload):
        list(osm_adapter.discover(make_discovery_request(external_categories=("amenity=dentist",))))


def test_osm_adapter_satisfies_shared_contract(osm_adapter):
    request = replace(
        make_discovery_request(external_categories=("amenity=dentist",)),
        dataset_version="2026-08-snapshot",
    )

    assert_adapter_contract(osm_adapter, request)


def test_osm_resolve_dataset_version_returns_configured_snapshot(osm_adapter):
    assert osm_adapter.resolve_dataset_version() == "2026-08-snapshot"


def test_osm_resolve_dataset_version_builds_stable_development_marker():
    clock_calls = 0

    def clock():
        nonlocal clock_calls
        clock_calls += 1
        return datetime(2026, 9, 4, 12, tzinfo=UTC)

    adapter = OpenStreetMapAdapter(
        client=RecordingOverpassClient({"elements": []}),
        endpoint_url=f" {ENDPOINT} ",
        dataset_version="",
        timeout_seconds=60,
        max_size_bytes=1024,
        clock=clock,
    )
    digest = hashlib.sha256(ENDPOINT.encode()).hexdigest()[:12]

    assert adapter.resolve_dataset_version() == (f"overpass-live:{digest}:2026-09-04T12:00:00Z")
    assert adapter.resolve_dataset_version() == (f"overpass-live:{digest}:2026-09-04T12:00:00Z")
    assert clock_calls == 1


def test_default_osm_adapter_requires_configured_endpoint(settings):
    settings.OVERPASS_URL = ""
    adapter = OpenStreetMapAdapter()

    with pytest.raises(PermanentSourceError) as raised:
        adapter.resolve_dataset_version()

    assert raised.value.code == "OVERPASS_NOT_CONFIGURED"


@pytest.mark.django_db
def test_default_operational_limits_come_from_osm_source(osm_source, osm_fixture):
    osm_source.timeout_seconds = 23
    osm_source.settings = {"max_size_bytes": 4096}
    osm_source.save(update_fields=("timeout_seconds", "settings"))
    client = RecordingOverpassClient(osm_fixture)
    adapter = OpenStreetMapAdapter(
        client=client,
        endpoint_url=ENDPOINT,
        dataset_version="2026-08-snapshot",
    )

    list(adapter.discover(make_discovery_request(external_categories=("amenity=dentist",))))

    assert "[timeout:23][maxsize:4096]" in client.queries[0]


@pytest.mark.django_db
def test_invalid_osm_source_settings_raise_classified_configuration_error(osm_source):
    osm_source.settings = ["not-an-object"]
    osm_source.save(update_fields=("settings",))
    adapter = OpenStreetMapAdapter(
        client=RecordingOverpassClient({"elements": []}),
        endpoint_url=ENDPOINT,
        dataset_version="2026-08-snapshot",
    )

    with pytest.raises(PermanentSourceError) as raised:
        list(adapter.discover(make_discovery_request(external_categories=("amenity=dentist",))))

    assert raised.value.code == "SOURCE_CONFIGURATION"


def test_default_registry_builds_osm_adapter_without_provider_io(settings):
    settings.OVERPASS_URL = ""

    adapter = get_adapter("osm")

    assert isinstance(adapter, OpenStreetMapAdapter)
    assert adapter.source_code == "osm"
