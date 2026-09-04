import pytest


@pytest.mark.django_db
def test_source_api_requires_authentication(api_client):
    response = api_client.get("/api/v1/sources/")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"


@pytest.mark.django_db
def test_source_api_exposes_only_public_configuration(auth_client, osm_source):
    assert osm_source.code == "osm"

    response = auth_client.get("/api/v1/sources/")

    assert response.status_code == 200
    item = next(row for row in response.json()["results"] if row["code"] == "osm")
    assert set(item) == {
        "id",
        "code",
        "name",
        "source_type",
        "is_paid",
        "is_active",
        "attribution",
        "license_code",
        "requests_per_second",
        "concurrency",
        "timeout_seconds",
        "max_retries",
    }
    assert item["attribution"] == "© OpenStreetMap contributors"
    assert item["license_code"] == "ODbL-1.0"
    assert item["requests_per_second"] == "0.20"
    assert item["concurrency"] == 1
    assert "settings" not in item
    assert "endpoint" not in item
