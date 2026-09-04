import os

import pytest

from apps.system.api import views


def test_suite_uses_testing_settings() -> None:
    assert os.environ["DJANGO_SETTINGS_MODULE"] == "config.settings.testing"


@pytest.mark.django_db
def test_live_health_does_not_require_auth(api_client):
    response = api_client.get("/api/v1/health/live/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_ready_health_reports_dependency_state(api_client):
    response = api_client.get("/api/v1/health/ready/")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "ok", "redis": "ok", "object_storage": "ok"},
    }


@pytest.mark.django_db
def test_ready_health_returns_503_without_exception_details(api_client, monkeypatch):
    def unavailable_redis() -> None:
        raise ConnectionError("redis://user:secret@redis:6379/0")

    monkeypatch.setattr(views, "check_redis", unavailable_redis)

    response = api_client.get("/api/v1/health/ready/")

    assert response.status_code == 503
    assert response.json() == {
        "status": "error",
        "checks": {"database": "ok", "redis": "error", "object_storage": "ok"},
    }
    assert "secret" not in response.content.decode()
