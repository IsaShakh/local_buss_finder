import pytest
from django.contrib.auth import get_user_model
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
