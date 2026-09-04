from uuid import uuid4

import pytest
from django.core.management import call_command

from apps.campaigns.domain import CreateCampaignCommand
from apps.campaigns.models import CampaignCategory, CampaignSource, DiscoveryCampaign
from apps.campaigns.services import create_campaign


def create_campaign_for(*, actor, alanya_area, source_ids, category_ids=(), name="Кампания"):
    return create_campaign(
        actor=actor,
        command=CreateCampaignCommand(
            name=name,
            search_area_id=alanya_area.id,
            source_ids=tuple(source_ids),
            category_ids=tuple(category_ids),
        ),
    )


@pytest.mark.django_db
def test_campaign_api_requires_authentication(api_client):
    response = api_client.get("/api/v1/campaigns/")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"


@pytest.mark.django_db
def test_campaign_api_creates_draft_from_exact_request(
    auth_client,
    alanya_area,
    overture_source,
    osm_source,
):
    call_command("seed_taxonomy")

    response = auth_client.post(
        "/api/v1/campaigns/",
        {
            "name": "Аланья — первичный сбор",
            "search_area_id": str(alanya_area.id),
            "source_ids": [str(overture_source.id), str(osm_source.id)],
            "category_ids": [],
        },
        format="json",
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {
        "id",
        "name",
        "status",
        "search_area",
        "sources",
        "categories",
        "total_jobs",
        "completed_jobs",
        "failed_jobs",
        "raw_records_found",
        "normalized_records",
        "rejected_records",
        "started_at",
        "finished_at",
        "created_at",
        "updated_at",
    }
    assert body["status"] == "draft"
    assert body["search_area"] == {"id": str(alanya_area.id), "name": "Аланья — пилот"}
    assert {source["code"] for source in body["sources"]} == {"overture", "osm"}
    assert body["categories"] == []
    assert (
        body["total_jobs"],
        body["completed_jobs"],
        body["failed_jobs"],
        body["raw_records_found"],
        body["normalized_records"],
        body["rejected_records"],
    ) == (0, 0, 0, 0, 0, 0)
    assert body["started_at"] is None
    assert body["finished_at"] is None
    assert "created_by" not in body
    assert "organization" not in body
    assert DiscoveryCampaign.objects.filter(id=body["id"]).exists()


@pytest.mark.django_db
def test_campaign_api_surfaces_domain_validation(auth_client, alanya_area):
    response = auth_client.post(
        "/api/v1/campaigns/",
        {
            "name": "Без источников",
            "search_area_id": str(alanya_area.id),
            "source_ids": [],
            "category_ids": [],
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "NO_SOURCES_SELECTED",
            "detail": "Выберите хотя бы один источник.",
            "fields": {"source_ids": ["Выберите хотя бы один источник."]},
        }
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("unknown_field", "error_code", "error_field", "error_message"),
    [
        (
            "search_area_id",
            "SEARCH_AREA_NOT_FOUND",
            "search_area_id",
            "Область поиска не найдена.",
        ),
        (
            "source_ids",
            "SOURCE_NOT_FOUND",
            "source_ids",
            "Один или несколько источников не найдены.",
        ),
        (
            "category_ids",
            "CATEGORY_NOT_FOUND",
            "category_ids",
            "Одна или несколько категорий не найдены.",
        ),
    ],
)
def test_campaign_api_rejects_unknown_references_in_standard_envelope(
    auth_client,
    alanya_area,
    osm_source,
    unknown_field,
    error_code,
    error_field,
    error_message,
):
    payload = {
        "name": "Неизвестная ссылка",
        "search_area_id": str(alanya_area.id),
        "source_ids": [str(osm_source.id)],
        "category_ids": [],
    }
    payload[unknown_field] = [str(uuid4())] if unknown_field.endswith("_ids") else str(uuid4())
    response = auth_client.post(
        "/api/v1/campaigns/",
        payload,
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == error_code
    assert response.json()["error"]["fields"] == {error_field: [error_message]}


@pytest.mark.django_db
def test_campaign_detail_hides_other_owners_campaign(
    api_client,
    other_owner,
    alanya_campaign,
):
    api_client.force_authenticate(other_owner)

    response = api_client.get(f"/api/v1/campaigns/{alanya_campaign.id}/")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.django_db
def test_campaign_list_returns_only_current_owners_rows(
    auth_client,
    owner,
    other_owner,
    alanya_area,
    osm_source,
):
    call_command("seed_taxonomy")
    create_campaign_for(
        actor=owner,
        alanya_area=alanya_area,
        source_ids=(osm_source.id,),
        name="Моя кампания",
    )
    create_campaign_for(
        actor=other_owner,
        alanya_area=alanya_area,
        source_ids=(osm_source.id,),
        name="Чужая кампания",
    )

    response = auth_client.get("/api/v1/campaigns/")

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["results"][0]["name"] == "Моя кампания"


@pytest.mark.django_db
def test_campaign_list_query_count_is_constant_for_ten_rows(
    auth_client,
    owner,
    alanya_area,
    osm_source,
    dentist_category,
    django_assert_num_queries,
):
    campaigns = DiscoveryCampaign.objects.bulk_create(
        [
            DiscoveryCampaign(
                name=f"Кампания {index}",
                created_by=owner,
                search_area=alanya_area,
            )
            for index in range(10)
        ]
    )
    CampaignSource.objects.bulk_create(
        [CampaignSource(campaign=campaign, source=osm_source) for campaign in campaigns]
    )
    CampaignCategory.objects.bulk_create(
        [CampaignCategory(campaign=campaign, category=dentist_category) for campaign in campaigns]
    )

    with django_assert_num_queries(4):
        response = auth_client.get("/api/v1/campaigns/")

    assert response.status_code == 200
    assert response.json()["count"] == 10
