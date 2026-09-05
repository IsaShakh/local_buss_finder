from dataclasses import replace
from types import SimpleNamespace

import pytest

from apps.discovery.domain import RawBusinessRecord
from apps.discovery.registry import get_adapter
from apps.sources.tests.fakes import InMemoryRawPayloadStore


class FixtureAdapter:
    source_code = "osm"

    def __init__(self, *, payloads=(), parsed=None, error=None):
        self.payloads = payloads
        self.parsed = parsed
        self.error = error
        self.requests = []
        self.resolve_calls = 0

    def resolve_dataset_version(self):
        self.resolve_calls += 1
        return "fixture-2026-09"

    def discover(self, request):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        yield from self.payloads

    def parse_payload(self, source_payload):
        if callable(self.parsed):
            return self.parsed(source_payload)
        if self.parsed is not None:
            return replace(self.parsed, external_id=source_payload.external_id)
        return RawBusinessRecord(
            external_id=source_payload.external_id,
            raw_name=str(source_payload.payload.get("name") or "Fixture business"),
            raw_category="amenity=dentist",
            raw_address="Saray, Alanya",
            raw_phones=(),
            raw_emails=(),
            raw_websites=(),
            raw_social_urls={},
            longitude=32.0,
            latitude=36.55,
        )


@pytest.fixture
def adapter_factory():
    def factory(*, payloads=(), parsed=None, error=None):
        return FixtureAdapter(payloads=payloads, parsed=parsed, error=error)

    return factory


@pytest.fixture
def fixture_adapter(adapter_factory, payload):
    second = replace(
        payload,
        external_id="node/43",
        payload={**payload.payload, "id": 43, "name": "Alanya Hotel"},
    )
    return adapter_factory(payloads=(payload, second))


@pytest.fixture
def fake_store():
    return InMemoryRawPayloadStore()


@pytest.fixture
def normalization_queue():
    return []


@pytest.fixture
def fixture_adapter_registry(settings):
    if not settings.DISCOVERY_USE_FIXTURES:
        pytest.fail("fixture adapters require the isolated E2E settings flag")
    return SimpleNamespace(get=get_adapter)


@pytest.fixture
def queued_source_run(single_source_draft_campaign, owner):
    from apps.campaigns.models import CampaignSourceRun
    from apps.campaigns.services import start_campaign

    campaign = start_campaign(
        campaign_id=single_source_draft_campaign.id,
        actor=owner,
        enqueue=lambda _: None,
    )
    return CampaignSourceRun.objects.get(campaign=campaign)
