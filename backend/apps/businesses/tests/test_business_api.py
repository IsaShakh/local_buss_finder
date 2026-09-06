import re
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.businesses.models import Business

pytestmark = pytest.mark.django_db
URL = "/api/v1/businesses/"
LIST_KEYS = {
    "id",
    "display_name",
    "category",
    "district",
    "address_text",
    "location",
    "phones",
    "emails",
    "websites",
    "social_urls",
    "source_count",
    "source_record_count",
    "pending_duplicate_count",
    "first_seen_at",
    "last_seen_at",
    "is_canonical",
}


def test_anonymous_business_routes_are_forbidden(api_client):
    assert api_client.get(URL).status_code == 403
    assert api_client.get(f"{URL}{uuid4()}/").status_code == 403


def test_business_list_and_detail_only_expose_active_owned_businesses(
    auth_client,
    business_factory,
    other_owner,
):
    target = business_factory()
    merged = Business.objects.create(owner=target.owner, merged_into=target)
    foreign = Business.objects.create(owner=other_owner)
    response = auth_client.get(URL)
    assert response.status_code == 200
    assert [row["id"] for row in response.json()["results"]] == [str(target.id)]
    missing = auth_client.get(f"{URL}{uuid4()}/")
    for business in (merged, foreign):
        response = auth_client.get(f"{URL}{business.id}/")
        assert response.status_code == missing.status_code == 404
        assert response.json() == missing.json()


def test_business_schema_and_distinct_counts_survive_membership_filters(
    auth_client,
    business_factory,
    candidate_factory,
    dentist_category,
):
    target = business_factory(sources=("osm", "osm", "overture"), category=dentist_category)
    other = business_factory(display_name="Other")
    candidate_factory(target, other)
    third = business_factory(display_name="Third")
    candidate_factory(target, third, status="rejected")
    source_record = target.memberships.first().normalized_record.source_record
    for params in (
        {},
        {"source": source_record.source.code},
        {
            "source": source_record.source.code,
            "campaign": str(source_record.campaign_id),
            "category": "dentist",
            "search": "SMILE",
        },
    ):
        response = auth_client.get(URL, params)
        assert response.status_code == 200
        rows = response.json()["results"]
        row = next(row for row in rows if row["id"] == str(target.id))
        assert len([row for row in rows if row["id"] == str(target.id)]) == 1
        assert set(row) == LIST_KEYS
        assert row["source_count"] == 2
        assert row["source_record_count"] == 3
        assert row["pending_duplicate_count"] == 1
        assert row["is_canonical"] is True
    for params in ({"campaign": str(uuid4())}, {"source": "missing"}, {"category": "missing"}):
        assert auth_client.get(URL, params).json()["count"] == 0


@pytest.mark.parametrize(
    "query",
    [
        "unknown=x",
        "page=0",
        "page=bad",
        "page_size=0",
        "page_size=101",
        "campaign=bad",
        "ordering=-display_name",
        "ordering=fetched_at",
        "search=",
        "source=bad%20source",
        "category=",
        "owner=1",
        "page=1&page=2",
    ],
)
def test_business_queries_are_strict(auth_client, query):
    assert auth_client.get(f"{URL}?{query}").status_code == 400


@pytest.mark.parametrize("url", [URL, "/api/v1/duplicate-candidates/"])
@pytest.mark.parametrize("parameter", ["page", "page_size"])
@pytest.mark.parametrize("value", ["1.0", "1.00", "+1", " 1 ", "01", "١"])
def test_canonical_lists_reject_noncanonical_pagination_integers(
    auth_client,
    url,
    parameter,
    value,
):
    response = auth_client.get(url, {parameter: value})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert parameter in response.json()["error"]["fields"]


@pytest.mark.parametrize("search", ["SMILE", "532123", "HELLO@", "clinic.example"])
def test_search_matches_canonical_name_and_contacts(auth_client, business_factory, search):
    target = business_factory(
        phones=["+905321234567"],
        emails=["hello@clinic.example"],
        websites=["https://clinic.example/contact"],
    )
    business_factory(display_name="Other", normalized_name="other", match_name="other")
    response = auth_client.get(URL, {"search": search})
    assert response.status_code == 200
    assert [row["id"] for row in response.json()["results"]] == [str(target.id)]


@pytest.mark.parametrize("search", ["' OR 1=1 --", "%", "_", "[", '"'])
def test_contact_search_treats_query_as_literal_value(auth_client, business_factory, search):
    business_factory(phones=["+905321234567"], emails=["hello@clinic.example"])
    response = auth_client.get(URL, {"search": search})
    assert response.status_code == 200
    assert response.json()["count"] == 0


@pytest.mark.parametrize(
    "ordering,reverse",
    [
        ("display_name", False),
        ("first_seen_at", False),
        ("-first_seen_at", True),
        ("last_seen_at", False),
        ("-last_seen_at", True),
        ("updated_at", False),
        ("-updated_at", True),
    ],
)
def test_business_ordering(auth_client, owner, ordering, reverse):
    earlier = datetime(2026, 9, 1, tzinfo=UTC)
    later = earlier + timedelta(days=1)
    a = Business.objects.create(
        owner=owner, display_name="Alpha", first_seen_at=earlier, last_seen_at=earlier
    )
    b = Business.objects.create(
        owner=owner, display_name="Beta", first_seen_at=later, last_seen_at=later
    )
    Business.objects.filter(pk=a.pk).update(updated_at=earlier)
    Business.objects.filter(pk=b.pk).update(updated_at=later)
    response = auth_client.get(URL, {"ordering": ordering})
    assert response.status_code == 200
    assert [row["id"] for row in response.json()["results"]] == (
        [str(b.id), str(a.id)] if reverse else [str(a.id), str(b.id)]
    )


def test_business_pagination_defaults_to_fifty_and_supports_one_hundred(auth_client, owner):
    Business.objects.bulk_create([Business(owner=owner) for _ in range(101)])
    default = auth_client.get(URL).json()
    assert default["count"] == 101
    assert len(default["results"]) == 50
    first = auth_client.get(URL, {"page_size": 100}).json()
    second = auth_client.get(URL, {"page_size": 100, "page": 2}).json()
    assert len(first["results"]) == 100
    assert len(second["results"]) == 1
    assert {row["id"] for row in first["results"]}.isdisjoint(
        row["id"] for row in second["results"]
    )


@pytest.mark.parametrize("filter_by_source", [False, True])
def test_business_pagination_projects_only_page_ids_after_narrow_count_and_slice(
    auth_client, business_factory, filter_by_source
):
    """Catches full-result aggregate work, wide DISTINCT, and lost page ordering."""
    businesses = [
        business_factory(display_name=name, sources=("osm", "osm", "overture"))
        for name in ("Alpha", "Beta", "Gamma", "Omega", "Zeta")
    ]
    filters = {}
    if filter_by_source:
        filters["source"] = (
            businesses[0].memberships.first().normalized_record.source_record.source.code
        )

    with CaptureQueriesContext(connection) as captured:
        response = auth_client.get(URL, {**filters, "page": 2, "page_size": 2})

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 5
    assert [row["id"] for row in body["results"]] == [
        str(businesses[2].id),
        str(businesses[3].id),
    ]
    assert [row["source_record_count"] for row in body["results"]] == [3, 3]
    assert [row["source_count"] for row in body["results"]] == [2, 2]
    queries = [entry["sql"] for entry in captured if entry["sql"].startswith("SELECT")]
    for narrow in queries[:2]:
        assert "COALESCE" not in narrow, narrow
        assert "SELECT DISTINCT" not in narrow, narrow
        assert "GROUP BY" not in narrow, narrow
    assert len(queries) == 3, queries
    count, page_ids, projection = queries
    assert re.match(r'SELECT "businesses_business"\."id"(?: AS "id")? FROM ', page_ids), page_ids
    assert "LIMIT 2 OFFSET 2" in page_ids
    if filters:
        assert "EXISTS" in count and "EXISTS" in page_ids
    assert projection.count("COALESCE") == 3
    assert '"businesses_business"."id" IN (' in projection
    for index, business in enumerate(businesses):
        assert (business.id.hex in projection.replace("-", "")) is (index in (2, 3))
    # Summary serialization must not load geography geometry or unused relations.
    assert '"geography_district"."geometry"' not in projection
    for relation in ("geography_country", "geography_province", "geography_neighborhood"):
        assert relation not in projection


def test_business_detail_includes_safe_provenance_and_canonical_geography(
    auth_client,
    business_factory,
):
    target = business_factory()
    membership = target.memberships.get()
    source_record = membership.normalized_record.source_record
    response = auth_client.get(f"{URL}{target.id}/")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == LIST_KEYS | {
        "country",
        "province",
        "neighborhood",
        "memberships",
        "memberships_truncated",
    }
    assert body["country"]["code"] == "TR"
    assert body["province"]["id"] == str(target.province_id)
    assert body["neighborhood"]["id"] == str(target.neighborhood_id)
    assert body["location"] == {"type": "Point", "coordinates": [32.5, 36.5]}
    assert body["memberships_truncated"] is False
    assert body["memberships"] == [
        {
            "id": str(membership.id),
            "source": {"code": source_record.source.code, "name": "osm"},
            "external_id": source_record.external_id,
            "campaign_id": str(source_record.campaign_id),
            "fetched_at": "2026-09-05T00:00:00Z",
            "source_dataset_version": "fixture-v1",
            "match_kind": "seed",
            "match_score": 0,
            "source_record_id": str(source_record.id),
            "source_record_url": f"/api/v1/source-records/{source_record.id}/",
        }
    ]
    provenance = auth_client.get(body["memberships"][0]["source_record_url"])
    assert provenance.status_code == 200
    assert provenance.json()["is_canonical"] is False
    assert provenance.json()["normalized"]["display_name"] == target.display_name


@pytest.mark.parametrize("count,truncated", [(100, False), (101, True)])
def test_business_detail_bounds_memberships_in_stable_fetch_order(
    auth_client,
    business_factory,
    count,
    truncated,
    django_assert_max_num_queries,
):
    target = business_factory(sources=("osm",) * count)
    memberships = list(target.memberships.order_by("id"))
    newest = memberships[-1].normalized_record.source_record
    newest.fetched_at = datetime(2026, 9, 6, tzinfo=UTC)
    newest.save(update_fields=("fetched_at",))
    with django_assert_max_num_queries(5):
        response = auth_client.get(f"{URL}{target.id}/")
    assert response.status_code == 200
    body = response.json()
    assert body["memberships_truncated"] is truncated
    assert len(body["memberships"]) == 100
    assert body["source_record_count"] == count
    assert [row["id"] for row in body["memberships"]] == [
        str(membership.id) for membership in [memberships[-1], *memberships[:-1]][:100]
    ]
