import logging
from uuid import UUID

import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_request_gets_safe_correlation_id(api_client):
    response = api_client.get(
        "/api/v1/health/live/",
        HTTP_X_CORRELATION_ID="campaign-ui-42",
    )

    assert response["X-Correlation-ID"] == "campaign-ui-42"


@pytest.mark.django_db
@pytest.mark.parametrize("unsafe", ["x\nforged", "x" * 129])
def test_unsafe_correlation_id_is_replaced(api_client, unsafe):
    response = api_client.get("/api/v1/health/live/", HTTP_X_CORRELATION_ID=unsafe)

    UUID(response["X-Correlation-ID"])


@pytest.mark.django_db
def test_csrf_failure_uses_safe_envelope_and_logs_no_credentials(caplog):
    caplog.set_level(logging.INFO)
    client = APIClient(enforce_csrf_checks=True)
    client.cookies["sessionid"] = "session-secret"

    response = client.post(
        "/api/v1/auth/login/",
        {"username": "private-owner", "password": "private-password"},
        format="json",
        HTTP_AUTHORIZATION="Bearer private-token",
    )

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "CSRF_FAILED",
            "detail": "Проверка CSRF не пройдена.",
            "fields": {},
        }
    }
    rendered = "\n".join(record.getMessage() for record in caplog.records)
    for forbidden in (
        "session-secret",
        "private-token",
        "private-owner",
        "private-password",
        "Traceback",
    ):
        assert forbidden not in rendered


@pytest.mark.django_db
def test_anonymous_session_error_contains_no_cookie_or_stack(api_client):
    api_client.cookies["sessionid"] = "session-secret"

    response = api_client.get("/api/v1/auth/session/")

    assert response.status_code == 403
    rendered = response.content.decode()
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"
    assert "session-secret" not in rendered
    assert "Traceback" not in rendered
