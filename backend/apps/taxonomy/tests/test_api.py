import pytest
from django.core.management import call_command

from apps.taxonomy.models import BusinessCategory


@pytest.mark.django_db
def test_category_api_requires_authentication(api_client):
    response = api_client.get("/api/v1/taxonomy/categories/")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"


@pytest.mark.django_db
def test_category_api_returns_nested_tree(auth_client, osm_source):
    assert osm_source.code == "osm"
    call_command("seed_taxonomy")

    response = auth_client.get("/api/v1/taxonomy/categories/")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 4
    roots = {item["slug"]: item for item in body["results"]}
    expected_tree = {
        "beauty": ("Красота", "beauty-salon", "Салон красоты"),
        "health": ("Медицина", "dentist", "Стоматология"),
        "hospitality": ("Гостеприимство", "hotel", "Отель"),
        "real-estate": (
            "Недвижимость",
            "real-estate-agency",
            "Агентство недвижимости",
        ),
    }
    assert set(roots) == set(expected_tree)
    for root_slug, (root_name, leaf_slug, leaf_name) in expected_tree.items():
        root = roots[root_slug]
        assert set(root) == {"id", "name", "slug", "children"}
        assert root["name"] == root_name
        assert len(root["children"]) == 1
        leaf = root["children"][0]
        assert set(leaf) == {"id", "name", "slug", "children"}
        assert (leaf["slug"], leaf["name"], leaf["children"]) == (
            leaf_slug,
            leaf_name,
            [],
        )
        assert "parent" not in leaf


@pytest.mark.django_db
def test_category_api_omits_inactive_roots_and_children(auth_client, osm_source):
    assert osm_source.code == "osm"
    call_command("seed_taxonomy")
    BusinessCategory.objects.filter(slug="hospitality").update(is_active=False)
    BusinessCategory.objects.filter(slug="beauty-salon").update(is_active=False)

    response = auth_client.get("/api/v1/taxonomy/categories/")

    roots = {item["slug"]: item for item in response.json()["results"]}
    assert "hospitality" not in roots
    assert roots["beauty"]["children"] == []
