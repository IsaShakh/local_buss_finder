import copy
import json
import re
import struct
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from apps.discovery.adapters.overture import OfficialOvertureClient, OvertureAdapter
from apps.discovery.domain import SourcePayload, SourceProvenance
from apps.discovery.errors import InvalidSourcePayload, PermanentSourceError, TransientSourceError
from apps.discovery.registry import get_adapter
from apps.discovery.tests.contracts import assert_adapter_contract
from apps.discovery.tests.fakes import make_discovery_request

FIXTURE_DIR = Path(__file__).resolve().parents[3] / "tests/fixtures/sources/overture"


@pytest.fixture
def taxonomy_payload():
    return json.loads((FIXTURE_DIR / "place_taxonomy.json").read_text())


@pytest.fixture
def legacy_payload():
    return json.loads((FIXTURE_DIR / "place_legacy_categories.json").read_text())


class RecordingOvertureClient:
    def __init__(
        self,
        rows=(),
        *,
        release="2026-08-19.0",
        latest_error=None,
        iteration_error=None,
    ):
        self.rows = tuple(rows)
        self.release = release
        self.latest_error = latest_error
        self.iteration_error = iteration_error
        self.latest_release_calls = 0
        self.requests = []

    def latest_release(self):
        self.latest_release_calls += 1
        if self.latest_error is not None:
            raise self.latest_error
        return self.release

    def iter_places(self, *, bbox, release):
        self.requests.append({"bbox": bbox, "release": release})
        if self.iteration_error is not None:
            raise self.iteration_error
        yield from self.rows


def make_payload(payload):
    return SourcePayload(
        external_id=payload["id"],
        payload=payload,
        fetched_at=datetime(2026, 9, 4, tzinfo=UTC),
        provenance=SourceProvenance(
            dataset_version="2026-08-19.0",
            source_url=None,
            attribution="Overture Maps Foundation",
            license_code="CDLA-Permissive-2.0/Apache-2.0",
        ),
    )


def test_overture_parser_prefers_new_taxonomy(taxonomy_payload):
    adapter = OvertureAdapter(client=RecordingOvertureClient())

    record = adapter.parse_payload(make_payload(taxonomy_payload))

    assert record.external_id == taxonomy_payload["id"]
    assert record.raw_category == "dentist"
    assert record.raw_name == "Alanya Test Diş Kliniği"
    assert (record.longitude, record.latitude) == (32.001, 36.544)


def test_overture_parser_uses_basic_category_when_taxonomy_is_missing(taxonomy_payload):
    payload = copy.deepcopy(taxonomy_payload)
    payload.pop("taxonomy")
    payload["basic_category"] = "dentist"
    adapter = OvertureAdapter(client=RecordingOvertureClient())

    record = adapter.parse_payload(make_payload(payload))

    assert record.raw_category == "dentist"


def test_overture_parser_falls_back_to_legacy_categories(legacy_payload):
    adapter = OvertureAdapter(client=RecordingOvertureClient())

    record = adapter.parse_payload(make_payload(legacy_payload))

    assert record.raw_category == "dentist"


def test_overture_parser_preserves_contact_order_and_groups_socials(taxonomy_payload):
    adapter = OvertureAdapter(client=RecordingOvertureClient())

    record = adapter.parse_payload(make_payload(taxonomy_payload))

    assert record.raw_address == "Saray Mah. Test Cad. No:1, Alanya"
    assert record.raw_phones == ("+90 242 000 00 01", "+90 242 000 00 02")
    assert record.raw_emails == (
        "hello@alanya-dentist.example",
        "booking@alanya-dentist.example",
    )
    assert record.raw_websites == (
        "https://alanya-dentist.example/",
        "https://booking.alanya-dentist.example/",
    )
    assert record.raw_social_urls == {
        "instagram": (
            "https://www.instagram.com/alanya_test_dentist",
            "https://instagram.com/alanya_test_dentist_en",
        ),
        "facebook": ("https://www.facebook.com/alanya.test.dentist",),
    }


def test_overture_parser_uses_empty_collections_and_none_for_missing_coordinates(
    taxonomy_payload,
):
    payload = copy.deepcopy(taxonomy_payload)
    for field in ("addresses", "phones", "emails", "websites", "socials", "geometry"):
        payload.pop(field)
    adapter = OvertureAdapter(client=RecordingOvertureClient())

    record = adapter.parse_payload(make_payload(payload))

    assert record.raw_address is None
    assert record.raw_phones == ()
    assert record.raw_emails == ()
    assert record.raw_websites == ()
    assert record.raw_social_urls == {}
    assert (record.longitude, record.latitude) == (None, None)


def test_overture_parser_preserves_numeric_coordinates_for_later_validation(taxonomy_payload):
    payload = copy.deepcopy(taxonomy_payload)
    payload["geometry"]["coordinates"] = [200.0, 95.0]
    adapter = OvertureAdapter(client=RecordingOvertureClient())

    record = adapter.parse_payload(make_payload(payload))

    assert (record.longitude, record.latitude) == (200.0, 95.0)


def test_overture_parser_treats_malformed_wkb_as_missing_coordinates(taxonomy_payload):
    payload = copy.deepcopy(taxonomy_payload)
    payload["geometry"] = {"$binary_hex": b"not-wkb".hex()}
    adapter = OvertureAdapter(client=RecordingOvertureClient())

    record = adapter.parse_payload(make_payload(payload))

    assert (record.longitude, record.latitude) == (None, None)


def test_overture_discover_uses_bbox_release_category_filter_and_result_limit(
    taxonomy_payload, legacy_payload
):
    cafe = copy.deepcopy(taxonomy_payload)
    cafe["id"] = "08f1a2b3c4d5e6f70000000000000003"
    cafe["taxonomy"]["primary"] = "cafe"
    third_dentist = copy.deepcopy(taxonomy_payload)
    third_dentist["id"] = "08f1a2b3c4d5e6f70000000000000004"
    client = RecordingOvertureClient((cafe, taxonomy_payload, legacy_payload, third_dentist))
    adapter = OvertureAdapter(client=client)
    request = replace(
        make_discovery_request(external_categories=("dentist",)),
        dataset_version="2026-08-19.0",
        result_limit=2,
    )

    payloads = list(adapter.discover(request))

    assert [payload.external_id for payload in payloads] == [
        taxonomy_payload["id"],
        legacy_payload["id"],
    ]
    assert client.requests == [
        {
            "bbox": (31.9, 36.4, 32.2, 36.7),
            "release": "2026-08-19.0",
        }
    ]
    assert payloads[0].payload == taxonomy_payload
    assert payloads[0].provenance.dataset_version == "2026-08-19.0"


def test_overture_discover_assigns_deterministic_synthetic_id_to_idless_row(taxonomy_payload):
    payload = copy.deepcopy(taxonomy_payload)
    payload.pop("id")
    request = replace(make_discovery_request(), dataset_version="2026-08-19.0")

    first = next(OvertureAdapter(client=RecordingOvertureClient((payload,))).discover(request))
    second = next(OvertureAdapter(client=RecordingOvertureClient((payload,))).discover(request))

    assert first.external_id == second.external_id
    assert re.fullmatch(r"invalid:[0-9a-f]{64}", first.external_id)
    with pytest.raises(InvalidSourcePayload):
        OvertureAdapter(client=RecordingOvertureClient()).parse_payload(first)


def test_overture_adapter_satisfies_shared_contract(taxonomy_payload):
    adapter = OvertureAdapter(client=RecordingOvertureClient((taxonomy_payload,)))
    request = replace(
        make_discovery_request(external_categories=("dentist",)),
        dataset_version="2026-08-19.0",
    )

    assert_adapter_contract(adapter, request)


def test_overture_resolve_dataset_version_classifies_timeout():
    adapter = OvertureAdapter(
        client=RecordingOvertureClient(latest_error=TimeoutError("STAC timed out"))
    )

    with pytest.raises(TransientSourceError) as raised:
        adapter.resolve_dataset_version()

    assert raised.value.code == "SOURCE_TIMEOUT"


def test_overture_resolve_dataset_version_classifies_invalid_release():
    adapter = OvertureAdapter(client=RecordingOvertureClient(release=""))

    with pytest.raises(PermanentSourceError) as raised:
        adapter.resolve_dataset_version()

    assert raised.value.code == "INVALID_SOURCE_PAYLOAD"


def test_overture_discover_classifies_network_failure():
    adapter = OvertureAdapter(
        client=RecordingOvertureClient(iteration_error=OSError("S3 unavailable"))
    )
    request = replace(make_discovery_request(), dataset_version="2026-08-19.0")

    with pytest.raises(TransientSourceError) as raised:
        list(adapter.discover(request))

    assert raised.value.code == "SOURCE_TIMEOUT"


def test_overture_discover_classifies_unknown_release_or_schema():
    adapter = OvertureAdapter(
        client=RecordingOvertureClient(iteration_error=ValueError("unknown release"))
    )
    request = replace(make_discovery_request(), dataset_version="missing-release")

    with pytest.raises(PermanentSourceError) as raised:
        list(adapter.discover(request))

    assert raised.value.code == "INVALID_SOURCE_PAYLOAD"


def test_official_client_streams_batches_and_makes_rows_json_compatible():
    calls = []
    point_wkb = struct.pack("<BIdd", 1, 1, 32.001, 36.544)

    class Batch:
        def to_pylist(self):
            return [
                {
                    "id": "08f1a2b3c4d5e6f70000000000000005",
                    "observed_at": datetime(2026, 9, 4, tzinfo=UTC),
                    "geometry": point_wkb,
                }
            ]

    def reader(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return iter((Batch(),))

    client = OfficialOvertureClient(
        timeout_seconds=23,
        latest_release_fn=lambda: "2026-08-19.0",
        record_batch_reader_fn=reader,
    )

    rows = list(
        client.iter_places(
            bbox=(31.9, 36.4, 32.2, 36.7),
            release="2026-08-19.0",
        )
    )

    assert calls == [
        {
            "args": ("place",),
            "kwargs": {
                "bbox": (31.9, 36.4, 32.2, 36.7),
                "release": "2026-08-19.0",
                "connect_timeout": 23,
                "request_timeout": 23,
                "stac": True,
            },
        }
    ]
    assert rows[0]["observed_at"] == "2026-09-04T00:00:00+00:00"
    assert json.loads(json.dumps(rows[0]))["id"] == "08f1a2b3c4d5e6f70000000000000005"

    parsed = OvertureAdapter(client=RecordingOvertureClient()).parse_payload(
        make_payload(
            {
                **rows[0],
                "names": {"primary": "Binary Geometry Test"},
                "taxonomy": {"primary": "dentist"},
            }
        )
    )
    assert (parsed.longitude, parsed.latitude) == (32.001, 36.544)


def test_default_registry_builds_overture_adapter_without_provider_io():
    adapter = get_adapter("overture")

    assert isinstance(adapter, OvertureAdapter)
    assert adapter.source_code == "overture"
