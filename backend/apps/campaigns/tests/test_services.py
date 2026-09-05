import pytest
from django.core.management import call_command

from apps.campaigns.domain import CampaignValidationError, CreateCampaignCommand
from apps.campaigns.models import DiscoveryCampaign
from apps.campaigns.services import create_campaign


@pytest.mark.django_db
def test_create_campaign_persists_sources_and_empty_categories_mean_all(
    owner,
    alanya_area,
    overture_source,
    osm_source,
):
    call_command("seed_taxonomy")

    campaign = create_campaign(
        actor=owner,
        command=CreateCampaignCommand(
            name="Аланья — первичный сбор",
            search_area_id=alanya_area.id,
            source_ids=(overture_source.id, osm_source.id),
            category_ids=(),
        ),
    )

    assert campaign.status == DiscoveryCampaign.Status.DRAFT
    assert campaign.created_by == owner
    assert campaign.search_area == alanya_area
    assert set(campaign.sources.values_list("code", flat=True)) == {"overture", "osm"}
    assert campaign.categories.count() == 0
    assert campaign.total_jobs == 0


@pytest.mark.django_db
def test_create_campaign_persists_selected_categories(
    owner,
    alanya_area,
    osm_source,
    dentist_category,
):
    campaign = create_campaign(
        actor=owner,
        command=CreateCampaignCommand(
            name="Стоматологии Аланьи",
            search_area_id=alanya_area.id,
            source_ids=(osm_source.id,),
            category_ids=(dentist_category.id,),
        ),
    )

    assert tuple(campaign.categories.values_list("slug", flat=True)) == ("dentist",)


@pytest.mark.django_db
def test_create_campaign_requires_at_least_one_source(owner, alanya_area):
    with pytest.raises(CampaignValidationError) as error:
        create_campaign(
            actor=owner,
            command=CreateCampaignCommand("Без источников", alanya_area.id, (), ()),
        )

    assert error.value.code == "NO_SOURCES_SELECTED"
    assert error.value.fields == {"source_ids": ["Выберите хотя бы один источник."]}


@pytest.mark.django_db
def test_create_campaign_rejects_inactive_source(owner, alanya_area, osm_source):
    osm_source.is_active = False
    osm_source.save(update_fields=("is_active",))

    with pytest.raises(CampaignValidationError) as error:
        create_campaign(
            actor=owner,
            command=CreateCampaignCommand(
                "Неактивный источник",
                alanya_area.id,
                (osm_source.id,),
                (),
            ),
        )

    assert error.value.code == "SOURCE_INACTIVE"


@pytest.mark.django_db
def test_campaign_rejects_source_without_active_mappings(
    owner,
    alanya_area,
    active_source_without_mappings,
):
    with pytest.raises(CampaignValidationError) as error:
        create_campaign(
            actor=owner,
            command=CreateCampaignCommand(
                "Некорректная кампания",
                alanya_area.id,
                (active_source_without_mappings.id,),
                (),
            ),
        )

    assert error.value.code == "SOURCE_HAS_NO_ACTIVE_MAPPINGS"
    assert error.value.fields == {
        "source_ids": ["Для источника нет активных сопоставлений категорий."]
    }
    assert DiscoveryCampaign.objects.count() == 0
