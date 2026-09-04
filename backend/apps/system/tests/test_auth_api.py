import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_login_creates_session_and_session_endpoint_returns_user(api_client):
    user = get_user_model().objects.create_user(
        username="owner",
        password="correct-password",
        first_name="Владелец",
    )

    response = api_client.post(
        "/api/v1/auth/login/",
        {"username": "owner", "password": "correct-password"},
        format="json",
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": user.id,
        "username": "owner",
        "display_name": "Владелец",
    }
    assert api_client.get("/api/v1/auth/session/").json() == response.json()


@pytest.mark.django_db
def test_invalid_login_uses_stable_english_code_and_russian_detail(api_client):
    response = api_client.post(
        "/api/v1/auth/login/",
        {"username": "owner", "password": "wrong"},
        format="json",
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "INVALID_CREDENTIALS",
            "detail": "Неверное имя пользователя или пароль.",
            "fields": {},
        }
    }


@pytest.mark.django_db
def test_session_endpoint_rejects_anonymous_user(api_client):
    response = api_client.get("/api/v1/auth/session/")

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "NOT_AUTHENTICATED",
            "detail": "Требуется вход.",
            "fields": {},
        }
    }


@pytest.mark.django_db
def test_logout_clears_session(api_client, owner):
    api_client.force_login(owner)

    response = api_client.post("/api/v1/auth/logout/")

    assert response.status_code == 204
    assert response.content == b""
    assert api_client.get("/api/v1/auth/session/").status_code == 403


@pytest.mark.django_db
def test_logout_requires_csrf_for_authenticated_session(owner):
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(owner)

    response = client.post("/api/v1/auth/logout/")

    assert response.status_code == 403


@pytest.mark.django_db
def test_login_requires_csrf_cookie_and_matching_header():
    client = APIClient(enforce_csrf_checks=True)
    get_user_model().objects.create_user(username="owner", password="correct-password")

    rejected = client.post(
        "/api/v1/auth/login/",
        {"username": "owner", "password": "correct-password"},
        format="json",
    )

    assert rejected.status_code == 403

    csrf_response = client.get("/api/v1/auth/csrf/")

    assert csrf_response.status_code == 200
    assert csrf_response.json() == {"detail": "CSRF cookie установлена."}
    token = client.cookies["csrftoken"].value

    accepted = client.post(
        "/api/v1/auth/login/",
        {"username": "owner", "password": "correct-password"},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )

    assert accepted.status_code == 200
