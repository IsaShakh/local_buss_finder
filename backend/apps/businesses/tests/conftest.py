from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.campaigns.domain import CreateCampaignCommand
from apps.campaigns.models import CampaignSourceRun, DiscoveryCampaign
from apps.campaigns.progress import finalize_source_run, try_finalize_campaign
from apps.campaigns.services import create_campaign, start_campaign
from apps.discovery.domain import RawBusinessRecord, SourcePayload, SourceProvenance
from apps.discovery.errors import InvalidSourcePayload
from apps.normalization.services import materialize_normalization
from apps.sources.models import SourceRecord
from apps.sources.services import persist_source_payload
from apps.sources.tests.fakes import InMemoryRawPayloadStore


@dataclass(frozen=True)
class RecordsFixture:
    target: SourceRecord
    rejected: SourceRecord
    failed: SourceRecord
    foreign: SourceRecord


def _create_campaign_run(*, actor, alanya_area, osm_source, name):
    call_command("seed_taxonomy")
    campaign = create_campaign(
        actor=actor,
        command=CreateCampaignCommand(
            name=name,
            search_area_id=alanya_area.id,
            source_ids=(osm_source.id,),
            category_ids=(),
        ),
    )
    campaign = start_campaign(campaign_id=campaign.id, actor=actor, enqueue=lambda _: None)
    campaign.status = DiscoveryCampaign.Status.RUNNING
    campaign.started_at = timezone.now()
    campaign.save(update_fields=("status", "started_at", "updated_at"))
    run = CampaignSourceRun.objects.get(campaign=campaign)
    run.status = CampaignSourceRun.Status.RUNNING
    run.started_at = timezone.now()
    run.save(update_fields=("status", "started_at", "updated_at"))
    return campaign, run


def _payload(number: int, *, name: str | None) -> SourcePayload:
    return SourcePayload(
        external_id=f"node/{number}",
        payload={"id": number, "name": name},
        fetched_at=datetime(2026, 9, 4, 9, number % 60, tzinfo=UTC),
        provenance=SourceProvenance(
            dataset_version="fixture-2026-09",
            source_url=f"https://www.openstreetmap.org/node/{number}",
            attribution="© OpenStreetMap contributors",
            license_code="ODbL-1.0",
        ),
    )


def _raw(number: int, *, name: str | None) -> RawBusinessRecord:
    return RawBusinessRecord(
        external_id=f"node/{number}",
        raw_name=name,
        raw_category="amenity=dentist",
        raw_address="Saray, Alanya",
        raw_phones=("0532 123 45 67",),
        raw_emails=(f"info{number}@example.test",),
        raw_websites=(f"HTTPS://Example.TEST/{number}#contact",),
        raw_social_urls={"instagram": (f"https://instagram.com/example{number}",)},
        longitude=32.0,
        latitude=36.55,
    )


def _persist_and_materialize(*, run, store, number: int, name: str | None) -> SourceRecord:
    payload = _payload(number, name=name)
    raw = _raw(number, name=name)
    persisted = persist_source_payload(
        source_run=run,
        source_payload=payload,
        parse_payload=lambda _: raw,
        store=store,
    )
    record = SourceRecord.objects.get(id=persisted.source_record_id)
    materialize_normalization(record.id)
    record.refresh_from_db()
    return record


def _persist_failed(*, run, store, number: int) -> SourceRecord:
    def fail_parser(_):
        raise InvalidSourcePayload("fixture parser rejected payload")

    persisted = persist_source_payload(
        source_run=run,
        source_payload=_payload(number, name="Broken"),
        parse_payload=fail_parser,
        store=store,
    )
    return SourceRecord.objects.get(id=persisted.source_record_id)


@pytest.fixture
def records(owner, other_owner, alanya_area, osm_source):
    store = InMemoryRawPayloadStore()
    _, owner_run = _create_campaign_run(
        actor=owner,
        alanya_area=alanya_area,
        osm_source=osm_source,
        name="Owner records",
    )
    target = _persist_and_materialize(
        run=owner_run,
        store=store,
        number=101,
        name="Alanya Smile Diş Kliniği",
    )
    rejected = _persist_and_materialize(
        run=owner_run,
        store=store,
        number=102,
        name=None,
    )
    failed = _persist_failed(run=owner_run, store=store, number=103)

    _, foreign_run = _create_campaign_run(
        actor=other_owner,
        alanya_area=alanya_area,
        osm_source=osm_source,
        name="Foreign records",
    )
    foreign = _persist_and_materialize(
        run=foreign_run,
        store=store,
        number=201,
        name="Foreign Smile",
    )
    return RecordsFixture(target=target, rejected=rejected, failed=failed, foreign=foreign)


@pytest.fixture
def normalized_records(records):
    run = records.target.source_run
    store = InMemoryRawPayloadStore()
    extra = [
        _persist_and_materialize(
            run=run,
            store=store,
            number=number,
            name=f"Business {number}",
        )
        for number in (104, 105)
    ]
    return [records.target, *extra]


@pytest.fixture
def fifty_normalized_records(owner, alanya_area, osm_source):
    _, run = _create_campaign_run(
        actor=owner,
        alanya_area=alanya_area,
        osm_source=osm_source,
        name="Fifty records",
    )
    store = InMemoryRawPayloadStore()
    return [
        _persist_and_materialize(
            run=run,
            store=store,
            number=1000 + index,
            name=f"Business {index:02d}",
        )
        for index in range(50)
    ]


@pytest.fixture
def campaign(owner, alanya_area, osm_source):
    campaign, run = _create_campaign_run(
        actor=owner,
        alanya_area=alanya_area,
        osm_source=osm_source,
        name="Dashboard campaign",
    )
    store = InMemoryRawPayloadStore()
    _persist_and_materialize(run=run, store=store, number=301, name="Smile One")
    _persist_and_materialize(run=run, store=store, number=302, name="Smile Two")
    _persist_and_materialize(run=run, store=store, number=303, name=None)
    run.refresh_from_db()
    run.status = CampaignSourceRun.Status.NORMALIZING
    run.discovery_finished_at = timezone.now()
    run.save(update_fields=("status", "discovery_finished_at", "updated_at"))
    finalize_source_run(source_run_id=run.id, status="completed")
    try_finalize_campaign(campaign.id)
    campaign.refresh_from_db()
    return campaign
