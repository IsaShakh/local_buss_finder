import os
from datetime import UTC, datetime
from uuid import uuid4

import boto3
import pytest
from botocore.config import Config
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APIClient


@pytest.fixture
def minio_store():
    if os.environ.get("STORAGE_INTEGRATION_PROJECT") != "1":
        pytest.fail("storage integration tests require the isolated Compose project")

    from apps.sources.storage import S3RawPayloadStore

    addressing_style = "path" if settings.S3_FORCE_PATH_STYLE else "auto"
    client = boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL,
        aws_access_key_id=settings.S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
        region_name=settings.S3_REGION_NAME,
        config=Config(s3={"addressing_style": addressing_style}),
    )
    bucket = f"lbi-storage-test-{uuid4().hex}"
    bucket_created = False
    try:
        client.create_bucket(Bucket=bucket)
        bucket_created = True
        yield S3RawPayloadStore(client=client, bucket=bucket)
    finally:
        if bucket_created:
            while True:
                objects = client.list_objects_v2(Bucket=bucket).get("Contents", [])
                if not objects:
                    break
                client.delete_objects(
                    Bucket=bucket,
                    Delete={"Objects": [{"Key": item["Key"]} for item in objects]},
                )
            client.delete_bucket(Bucket=bucket)


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def owner(db):
    return get_user_model().objects.create_user(
        username="owner",
        password="correct-password",
        first_name="Владелец",
    )


@pytest.fixture
def auth_client(owner) -> APIClient:
    client = APIClient()
    client.force_authenticate(owner)
    return client


@pytest.fixture
def alanya_area(db):
    from apps.geography.models import SearchArea

    call_command("seed_reference_data")
    return SearchArea.objects.get(name="Аланья — пилот")


@pytest.fixture
def overture_source(db):
    from apps.sources.models import Source

    call_command("seed_sources")
    return Source.objects.get(code="overture")


@pytest.fixture
def osm_source(db):
    from apps.sources.models import Source

    call_command("seed_sources")
    return Source.objects.get(code="osm")


@pytest.fixture
def dentist_category(db):
    from apps.taxonomy.models import BusinessCategory

    call_command("seed_sources")
    call_command("seed_taxonomy")
    return BusinessCategory.objects.get(slug="dentist")


@pytest.fixture
def active_source_without_mappings(db):
    from apps.sources.models import Source

    return Source.objects.create(
        code="fixture-empty",
        name="Fixture Empty",
        source_type=Source.Type.OPEN_DATA,
        attribution="fixture",
        license_code="fixture-only",
    )


@pytest.fixture
def other_owner(db):
    return get_user_model().objects.create_user(username="other-owner")


@pytest.fixture
def alanya_campaign(owner, alanya_area, overture_source, osm_source):
    from apps.campaigns.domain import CreateCampaignCommand
    from apps.campaigns.services import create_campaign

    call_command("seed_taxonomy")
    return create_campaign(
        actor=owner,
        command=CreateCampaignCommand(
            name="Аланья — первичный сбор",
            search_area_id=alanya_area.id,
            source_ids=(overture_source.id, osm_source.id),
            category_ids=(),
        ),
    )


@pytest.fixture
def campaign(alanya_campaign):
    return alanya_campaign


@pytest.fixture
def source_run(alanya_campaign, osm_source):
    from apps.campaigns.models import CampaignSourceRun

    return CampaignSourceRun.objects.get_or_create(
        campaign=alanya_campaign,
        source=osm_source,
    )[0]


@pytest.fixture
def payload():
    from apps.sources.domain import SourcePayload, SourceProvenance

    return SourcePayload(
        external_id="node/42",
        payload={"id": 42, "name": "Alanya Diş", "tags": {"amenity": "dentist"}},
        fetched_at=datetime(2026, 9, 4, 9, 30, tzinfo=UTC),
        provenance=SourceProvenance(
            dataset_version="fixture-2026-09",
            source_url="https://www.openstreetmap.org/node/42",
            attribution="© OpenStreetMap contributors",
            license_code="ODbL-1.0",
        ),
    )


@pytest.fixture
def parsed():
    from apps.sources.domain import RawBusinessRecord

    return RawBusinessRecord(
        external_id="node/42",
        raw_name="Alanya Diş",
        raw_category="dentist",
        raw_address="Saray, Alanya",
        raw_phones=("+90 242 555 0101",),
        raw_emails=("info@example.test",),
        raw_websites=("https://example.test",),
        raw_social_urls={"instagram": ("https://instagram.com/example",)},
        longitude=32.0,
        latitude=36.55,
    )


@pytest.fixture
def store():
    from apps.sources.tests.fakes import InMemoryRawPayloadStore

    return InMemoryRawPayloadStore()


@pytest.fixture
def thread_safe_store():
    from apps.sources.tests.fakes import InMemoryRawPayloadStore

    return InMemoryRawPayloadStore()
