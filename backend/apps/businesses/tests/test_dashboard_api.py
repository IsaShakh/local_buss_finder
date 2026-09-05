import pytest


@pytest.mark.django_db
def test_dashboard_summary_uses_persisted_campaign_and_record_counts(auth_client, campaign):
    response = auth_client.get("/api/v1/dashboard/summary/")

    assert response.status_code == 200
    assert response.json() == {
        "records": {"raw": 3, "normalized": 2, "rejected": 1, "failed": 0},
        "campaigns": {"total": 1, "running": 0, "with_errors": 0},
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
