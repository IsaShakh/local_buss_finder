from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest

from apps.discovery.domain import BoundingBox, SourcePayload, SourceProvenance
from apps.discovery.errors import (
    InvalidSourcePayload,
    PermanentSourceError,
    RateLimitedSourceError,
    TransientSourceError,
    UnknownDiscoveryAdapter,
)
from apps.discovery.registry import get_adapter
from apps.discovery.tests.contracts import assert_adapter_contract
from apps.discovery.tests.fakes import make_contract_adapter, make_discovery_request


def test_registry_returns_adapter_configured_for_source(settings):
    settings.DISCOVERY_USE_FIXTURES = True
    settings.DISCOVERY_ADAPTERS = {"fixture": "apps.discovery.tests.fakes.FixtureDiscoveryAdapter"}

    adapter = get_adapter("fixture")

    assert adapter.source_code == "fixture"


def test_registry_returns_new_adapter_for_each_source_run(settings):
    settings.DISCOVERY_USE_FIXTURES = True
    settings.DISCOVERY_ADAPTERS = {"fixture": "apps.discovery.tests.fakes.FixtureDiscoveryAdapter"}

    first = get_adapter("fixture")
    second = get_adapter("fixture")

    assert first is not second


def test_registry_rejects_unknown_source(settings):
    settings.DISCOVERY_ADAPTERS = {}

    with pytest.raises(UnknownDiscoveryAdapter) as raised:
        get_adapter("missing")

    assert raised.value.code == "UNKNOWN_DISCOVERY_ADAPTER"
    assert raised.value.detail == "missing"
    assert raised.value.source_code == "missing"


def test_registry_rejects_test_adapter_without_fixture_mode(settings):
    settings.DISCOVERY_USE_FIXTURES = False
    settings.DISCOVERY_ADAPTERS = {"fixture": "apps.discovery.tests.fakes.FixtureDiscoveryAdapter"}

    with pytest.raises(UnknownDiscoveryAdapter):
        get_adapter("fixture")


def test_contract_probe_executes_shared_contract():
    assert_adapter_contract(
        make_contract_adapter(),
        make_discovery_request(external_categories=("dentist",)),
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("west", -181.0),
        ("east", 181.0),
        ("south", -91.0),
        ("north", 91.0),
        ("west", 32.2),
        ("south", 36.7),
    ],
)
def test_bounding_box_rejects_invalid_wgs84_extent(field, value):
    coordinates = {"west": 31.9, "south": 36.4, "east": 32.2, "north": 36.7}
    coordinates[field] = value

    with pytest.raises(ValueError):
        BoundingBox(**coordinates)


@pytest.mark.parametrize("dataset_version", ["", "   "])
def test_discovery_request_rejects_empty_dataset_version(dataset_version):
    request = make_discovery_request()

    with pytest.raises(ValueError):
        replace(request, dataset_version=dataset_version)


@pytest.mark.parametrize("result_limit", [0, -1])
def test_discovery_request_rejects_non_positive_result_limit(result_limit):
    request = make_discovery_request()

    with pytest.raises(ValueError):
        replace(request, result_limit=result_limit)


def test_discovery_request_rejects_empty_external_categories():
    with pytest.raises(ValueError):
        make_discovery_request(external_categories=())


@pytest.mark.parametrize("correlation_id", ["", "   "])
def test_discovery_request_rejects_empty_correlation_id(correlation_id):
    request = make_discovery_request()

    with pytest.raises(ValueError):
        replace(request, correlation_id=correlation_id)


def test_domain_value_objects_are_frozen():
    request = make_discovery_request()
    payload = next(make_contract_adapter().discover(request))
    parsed = make_contract_adapter().parse_payload(payload)
    values_and_fields = (
        (request.bbox, "west"),
        (request, "dataset_version"),
        (payload.provenance, "attribution"),
        (payload, "external_id"),
        (parsed, "raw_name"),
    )

    for value, field in values_and_fields:
        with pytest.raises(FrozenInstanceError):
            setattr(value, field, "changed")


def test_typed_discovery_errors_keep_machine_readable_context():
    transient = TransientSourceError("SOURCE_TIMEOUT", "provider timed out")
    rate_limited = RateLimitedSourceError(retry_after_seconds=17)
    permanent = PermanentSourceError("SOURCE_CONFIGURATION", "missing token")
    invalid_payload = InvalidSourcePayload("missing external id")

    assert (transient.code, transient.detail) == ("SOURCE_TIMEOUT", "provider timed out")
    assert (rate_limited.code, rate_limited.retry_after_seconds) == (
        "SOURCE_RATE_LIMITED",
        17,
    )
    assert (permanent.code, permanent.detail) == ("SOURCE_CONFIGURATION", "missing token")
    assert (invalid_payload.code, invalid_payload.detail) == (
        "INVALID_SOURCE_PAYLOAD",
        "missing external id",
    )


def test_payload_accepts_json_compatible_provider_data():
    payload = SourcePayload(
        external_id="fixture/42",
        payload={"active": True, "score": 4.5, "tags": ["dentist", None]},
        fetched_at=datetime(2026, 9, 4, 9, 30, tzinfo=UTC),
        provenance=SourceProvenance(
            dataset_version="fixture-2026-09",
            source_url=None,
            attribution="Fixture data",
            license_code="TEST-1.0",
        ),
    )

    assert payload.payload == {
        "active": True,
        "score": 4.5,
        "tags": ["dentist", None],
    }
