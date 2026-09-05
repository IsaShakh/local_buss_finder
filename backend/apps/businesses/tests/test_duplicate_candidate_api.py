from uuid import uuid4

import pytest

from apps.businesses.models import Business, DuplicateCandidate

pytestmark = pytest.mark.django_db
URL = "/api/v1/duplicate-candidates/"


@pytest.mark.parametrize("action", ["confirm", "reject"])
def test_candidate_routes_require_authentication(api_client, action):
    assert api_client.get(URL).status_code == 403
    assert api_client.post(f"{URL}{uuid4()}/{action}/", {}, format="json").status_code == 403


def test_pending_list_is_owned_active_ordered_and_explained(
    auth_client,
    business_factory,
    candidate_factory,
    other_owner,
    django_assert_max_num_queries,
):
    a, b, c, d = [business_factory(display_name=name) for name in ("A", "B", "C", "D")]
    pending = candidate_factory(
        a,
        b,
        score=70,
        signals=[
            {"code": "exact_phone", "weight": 35, "value": None},
            {"code": "incompatible_category", "weight": -25, "value": None},
        ],
    )
    highest = candidate_factory(a, c, score=90)
    for status, pair in [("rejected", (b, c)), ("confirmed", (b, d)), ("superseded", (c, d))]:
        candidate_factory(*pair, status=status)
    merged = Business.objects.create(owner=a.owner, merged_into=a)
    candidate_factory(a, merged, score=100)
    foreign = [Business.objects.create(owner=other_owner) for _ in range(2)]
    candidate_factory(*foreign, owner=other_owner, score=100)
    with django_assert_max_num_queries(5):
        response = auth_client.get(URL)
    assert response.status_code == 200
    assert response.json()["count"] == 2
    rows = response.json()["results"]
    assert [row["id"] for row in rows] == [str(highest.id), str(pending.id)]
    row = rows[1]
    assert set(row) == {
        "id",
        "left_business",
        "right_business",
        "score",
        "signals",
        "created_at",
        "updated_at",
    }
    assert {row["left_business"]["id"], row["right_business"]["id"]} == {str(a.id), str(b.id)}
    assert {row["left_business"]["display_name"], row["right_business"]["display_name"]} == {
        "A",
        "B",
    }
    assert row["left_business"]["source_record_count"] == 1
    assert row["signals"] == [
        {"code": "exact_phone", "weight": 35, "value": None, "label": "Совпадает телефон"},
        {
            "code": "incompatible_category",
            "weight": -25,
            "value": None,
            "label": "Разные категории",
        },
    ]


@pytest.mark.parametrize("query", ["status=rejected", "owner=1", "page_size=101", "page=0"])
def test_candidate_list_rejects_unsupported_queries(auth_client, query):
    assert auth_client.get(f"{URL}?{query}").status_code == 400


def test_candidate_pagination_accepts_digit_integers_with_default_and_maximum_sizes(
    auth_client,
    owner,
    candidate_factory,
):
    businesses = Business.objects.bulk_create([Business(owner=owner) for _ in range(102)])
    for business in businesses[1:]:
        candidate_factory(businesses[0], business)

    default = auth_client.get(URL)
    first = auth_client.get(URL, {"page_size": "100", "page": "1"})
    second = auth_client.get(URL, {"page_size": "100", "page": "2"})
    single = auth_client.get(URL, {"page_size": "1", "page": "1"})

    assert (
        default.status_code == first.status_code == second.status_code == single.status_code == 200
    )
    assert default.json()["count"] == 101
    assert len(default.json()["results"]) == 50
    assert len(first.json()["results"]) == 100
    assert len(second.json()["results"]) == len(single.json()["results"]) == 1
    assert {row["id"] for row in first.json()["results"]}.isdisjoint(
        row["id"] for row in second.json()["results"]
    )


@pytest.mark.parametrize("action", ["confirm", "reject"])
def test_decision_persists_real_effects_and_repeated_decision_conflicts(
    auth_client,
    business_factory,
    candidate_factory,
    owner,
    action,
):
    a = business_factory(sources=("osm", "overture"))
    b = business_factory()
    candidate = candidate_factory(a, b)
    response = auth_client.post(f"{URL}{candidate.id}/{action}/", {}, format="json")
    assert response.status_code == 200
    candidate.refresh_from_db()
    b.refresh_from_db()
    assert candidate.status == ("confirmed" if action == "confirm" else "rejected")
    assert candidate.decided_by_id == owner.id
    assert candidate.decided_at is not None
    assert response.json() == {
        "id": str(candidate.id),
        "status": candidate.status,
        "survivor_business_id": str(a.id) if action == "confirm" else None,
        "merged_business_id": str(b.id) if action == "confirm" else None,
    }
    assert b.merged_into_id == (a.id if action == "confirm" else None)
    assert a.memberships.count() == (3 if action == "confirm" else 2)
    stale = auth_client.post(f"{URL}{candidate.id}/{action}/", {}, format="json")
    assert stale.status_code == 409
    assert stale.json() == {"code": "DUPLICATE_CANDIDATE_NOT_PENDING"}
    assert auth_client.get(URL).json()["count"] == 0


@pytest.mark.parametrize("action", ["confirm", "reject"])
def test_decisions_hide_foreign_candidate_and_reject_client_survivor(
    auth_client,
    business_factory,
    candidate_factory,
    other_owner,
    action,
):
    a, b = business_factory(), business_factory()
    candidate = candidate_factory(a, b)
    invalid = auth_client.post(
        f"{URL}{candidate.id}/{action}/", {"survivor_business_id": str(b.id)}, format="json"
    )
    assert invalid.status_code == 400
    candidate.refresh_from_db()
    assert candidate.status == "pending"
    foreign = [Business.objects.create(owner=other_owner) for _ in range(2)]
    foreign_candidate = candidate_factory(*foreign, owner=other_owner)
    response = auth_client.post(f"{URL}{foreign_candidate.id}/{action}/", {}, format="json")
    missing = auth_client.post(f"{URL}{uuid4()}/{action}/", {}, format="json")
    assert response.status_code == missing.status_code == 404
    assert response.json() == missing.json()
    foreign_candidate.refresh_from_db()
    assert foreign_candidate.status == DuplicateCandidate.Status.PENDING


@pytest.mark.parametrize("action", ["confirm", "reject"])
def test_decisions_on_pairs_with_merged_businesses_conflict(
    auth_client,
    business_factory,
    candidate_factory,
    action,
):
    a, b = business_factory(), business_factory()
    candidate = candidate_factory(a, b)
    b.merged_into = a
    b.save(update_fields=("merged_into",))
    response = auth_client.post(f"{URL}{candidate.id}/{action}/", {}, format="json")
    assert response.status_code == 409
    assert response.json() == {"code": "DUPLICATE_CANDIDATE_NOT_PENDING"}
