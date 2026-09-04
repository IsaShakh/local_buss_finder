import pytest
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404

from apps.system.api.exceptions import api_exception_handler


def test_method_not_allowed_uses_the_common_error_envelope(api_client):
    response = api_client.post("/api/v1/health/live/")

    assert response.status_code == 405
    assert response.json() == {
        "error": {
            "code": "METHOD_NOT_ALLOWED",
            "detail": "Метод не разрешён.",
            "fields": {},
        }
    }


@pytest.mark.django_db
def test_serializer_validation_uses_the_common_error_envelope(api_client):
    response = api_client.post(
        "/api/v1/auth/login/",
        {"username": "owner"},
        format="json",
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["detail"] == "Проверьте правильность заполнения полей."
    assert set(body["error"]["fields"]) == {"password"}
    assert all(isinstance(message, str) for message in body["error"]["fields"]["password"])


@pytest.mark.parametrize(
    ("exception", "status_code", "code", "detail"),
    [
        (Http404(), 404, "NOT_FOUND", "Ресурс не найден."),
        (DjangoPermissionDenied(), 403, "PERMISSION_DENIED", "Недостаточно прав."),
    ],
)
def test_django_exceptions_use_the_common_error_envelope(
    exception,
    status_code,
    code,
    detail,
):
    response = api_exception_handler(exception, {})

    assert response is not None
    assert response.status_code == status_code
    assert response.data == {
        "error": {
            "code": code,
            "detail": detail,
            "fields": {},
        }
    }
