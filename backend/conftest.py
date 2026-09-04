import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APIClient


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
