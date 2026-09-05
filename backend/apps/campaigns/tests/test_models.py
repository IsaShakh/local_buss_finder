from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.campaigns.models import (
    CampaignCategory,
    CampaignSource,
    CampaignSourceRun,
    DiscoveryCampaign,
)


def create_campaign_row(owner, alanya_area):
    return DiscoveryCampaign.objects.create(
        name="Аланья — тест",
        created_by=owner,
        search_area=alanya_area,
    )


@pytest.mark.django_db
def test_campaign_source_uses_safe_operational_defaults(owner, alanya_area, osm_source):
    selection = CampaignSource.objects.create(
        campaign=create_campaign_row(owner, alanya_area),
        source=osm_source,
    )

    assert selection.is_enabled is True
    assert selection.priority == 100
    assert selection.request_limit is None
    assert selection.budget_limit is None


@pytest.mark.django_db
def test_free_source_rejects_nonzero_budget(owner, alanya_area, osm_source):
    selection = CampaignSource(
        campaign=create_campaign_row(owner, alanya_area),
        source=osm_source,
        budget_limit=Decimal("0.01"),
    )

    with pytest.raises(ValidationError, match="бесплатного источника"):
        selection.full_clean()


@pytest.mark.django_db
def test_source_run_initializes_progress_and_retry_budget(source_run):
    assert source_run.status == CampaignSourceRun.Status.PENDING
    assert source_run.source_retry_count == 0
    assert source_run.request_count == 0
    assert source_run.cost == Decimal(0)
    assert (
        source_run.discovered_records,
        source_run.stored_records,
        source_run.normalized_records,
        source_run.rejected_records,
        source_run.failed_records,
    ) == (0, 0, 0, 0, 0)
    assert source_run.source_dataset_version is None
    assert source_run.started_at is None
    assert source_run.discovery_finished_at is None
    assert source_run.finished_at is None
    assert source_run.error_code is None
    assert source_run.error_detail is None


@pytest.mark.django_db
def test_campaign_source_is_unique(owner, alanya_area, osm_source):
    campaign = create_campaign_row(owner, alanya_area)
    CampaignSource.objects.create(campaign=campaign, source=osm_source)

    with pytest.raises(IntegrityError), transaction.atomic():
        CampaignSource.objects.create(campaign=campaign, source=osm_source)


@pytest.mark.django_db
def test_campaign_category_is_unique(owner, alanya_area, dentist_category):
    campaign = create_campaign_row(owner, alanya_area)
    CampaignCategory.objects.create(campaign=campaign, category=dentist_category)

    with pytest.raises(IntegrityError), transaction.atomic():
        CampaignCategory.objects.create(campaign=campaign, category=dentist_category)


@pytest.mark.django_db
def test_source_run_is_unique(owner, alanya_area, osm_source):
    campaign = create_campaign_row(owner, alanya_area)
    CampaignSourceRun.objects.create(campaign=campaign, source=osm_source)

    with pytest.raises(IntegrityError), transaction.atomic():
        CampaignSourceRun.objects.create(campaign=campaign, source=osm_source)


@pytest.mark.django_db
def test_database_rejects_more_finished_jobs_than_total(owner, alanya_area):
    with pytest.raises(IntegrityError), transaction.atomic():
        DiscoveryCampaign.objects.create(
            name="Некорректный прогресс",
            created_by=owner,
            search_area=alanya_area,
            total_jobs=1,
            completed_jobs=1,
            failed_jobs=1,
        )
