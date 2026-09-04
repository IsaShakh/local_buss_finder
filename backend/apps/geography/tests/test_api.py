import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_search_area_api_requires_authentication(api_client):
    anonymous = api_client.get("/api/v1/geography/search-areas/")

    assert anonymous.status_code == 403
    assert anonymous.json()["error"]["code"] == "NOT_AUTHENTICATED"


@pytest.mark.django_db
def test_search_area_api_returns_geojson_bbox(auth_client):
    call_command("seed_reference_data")
    response = auth_client.get("/api/v1/geography/search-areas/")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    item = body["results"][0]
    assert item["name"] == "Аланья — пилот"
    assert item["bbox"] == [31.7, 36.3, 32.65, 36.75]
    assert item["geometry"]["type"] == "MultiPolygon"
    assert item["country"]["code"] == "TR"
    assert item["province"]["code"] == "07"
    assert item["district"]["slug"] == "alanya"
    assert item["neighborhood"] is None
