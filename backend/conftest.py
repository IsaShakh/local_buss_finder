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
