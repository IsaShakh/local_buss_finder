import pytest


@pytest.mark.django_db
def test_dashboard_summary_uses_persisted_campaign_and_record_counts(auth_client, campaign):
    response = auth_client.get("/api/v1/dashboard/summary/")

    assert response.status_code == 200
    assert response.json() == {
        "records": {"raw": 3, "normalized": 2, "rejected": 1, "failed": 0},
        "campaigns": {"total": 1, "running": 0, "with_errors": 0},
        "businesses": {"active": 2, "pending_duplicates": 1},
        "recent_campaigns": [
            {
                "id": str(campaign.id),
                "name": campaign.name,
                "status": "completed",
                "normalized": 2,
                "updated_at": campaign.updated_at.isoformat().replace("+00:00", "Z"),
            }
        ],
    }


@pytest.mark.django_db
def test_dashboard_summary_is_owner_scoped(
    auth_client,
    campaign,
    other_owner,
    alanya_area,
    osm_source,
):
    from apps.businesses.tests.conftest import _create_campaign_run

    _create_campaign_run(
        actor=other_owner,
        alanya_area=alanya_area,
        osm_source=osm_source,
        name="Foreign dashboard campaign",
    )

    response = auth_client.get("/api/v1/dashboard/summary/")

    assert response.status_code == 200
    assert response.json()["campaigns"]["total"] == 1
    assert response.json()["records"]["raw"] == 3


@pytest.mark.django_db
def test_dashboard_excludes_merged_foreign_and_nonpending_candidates(
    auth_client,
    campaign,
    other_owner,
    candidate_factory,
):
    from apps.businesses.models import Business, DuplicateCandidate

    active = list(Business.active.filter(owner=campaign.created_by))
    assert len(active) == 2
    DuplicateCandidate.objects.filter(owner=campaign.created_by).update(status="rejected")
    merged = Business.objects.create(owner=campaign.created_by, merged_into=active[0])
    candidate_factory(active[0], merged)
    foreign = [Business.objects.create(owner=other_owner) for _ in range(2)]
    candidate_factory(*foreign, owner=other_owner)
    response = auth_client.get("/api/v1/dashboard/summary/")
    assert response.status_code == 200
    assert response.json()["records"] == {"raw": 3, "normalized": 2, "rejected": 1, "failed": 0}
    assert response.json()["businesses"] == {"active": 2, "pending_duplicates": 0}
