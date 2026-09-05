from collections.abc import Callable, Iterable
from uuid import UUID

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction

from apps.campaigns.domain import CampaignValidationError, CreateCampaignCommand
from apps.campaigns.models import (
    CampaignCategory,
    CampaignSource,
    CampaignSourceRun,
    DiscoveryCampaign,
)
from apps.geography.models import SearchArea
from apps.sources.models import Source
from apps.taxonomy.models import BusinessCategory
from apps.taxonomy.services import resolve_external_categories
from common.observability import structured_event

type Enqueue = Callable[[UUID], None]


def _unique_ids(values: Iterable[UUID]) -> tuple[UUID, ...]:
    return tuple(dict.fromkeys(values))


@transaction.atomic
def create_campaign(
    *,
    actor: AbstractBaseUser,
    command: CreateCampaignCommand,
) -> DiscoveryCampaign:
    source_ids = _unique_ids(command.source_ids)
    category_ids = _unique_ids(command.category_ids)
    if not source_ids:
        raise CampaignValidationError(
            "NO_SOURCES_SELECTED",
            "Выберите хотя бы один источник.",
            {"source_ids": ["Выберите хотя бы один источник."]},
        )

    search_area = SearchArea.objects.filter(id=command.search_area_id).first()
    if search_area is None:
        raise CampaignValidationError(
            "SEARCH_AREA_NOT_FOUND",
            "Область поиска не найдена.",
            {"search_area_id": ["Область поиска не найдена."]},
        )

    sources = Source.objects.in_bulk(source_ids)
    if len(sources) != len(source_ids):
        raise CampaignValidationError(
            "SOURCE_NOT_FOUND",
            "Один или несколько источников не найдены.",
            {"source_ids": ["Один или несколько источников не найдены."]},
        )
    if any(not sources[source_id].is_active for source_id in source_ids):
        raise CampaignValidationError(
            "SOURCE_INACTIVE",
            "Выбран неактивный источник.",
            {"source_ids": ["Выберите только активные источники."]},
        )

    categories = BusinessCategory.objects.in_bulk(category_ids)
    if len(categories) != len(category_ids):
        raise CampaignValidationError(
            "CATEGORY_NOT_FOUND",
            "Одна или несколько категорий не найдены.",
            {"category_ids": ["Одна или несколько категорий не найдены."]},
        )
    if any(not categories[category_id].is_active for category_id in category_ids):
        raise CampaignValidationError(
            "CATEGORY_INACTIVE",
            "Выбрана неактивная категория.",
            {"category_ids": ["Выберите только активные категории."]},
        )

    for source_id in source_ids:
        if not resolve_external_categories(source_id, category_ids):
            raise CampaignValidationError(
                "SOURCE_HAS_NO_ACTIVE_MAPPINGS",
                "Для источника нет активных сопоставлений категорий.",
                {"source_ids": ["Для источника нет активных сопоставлений категорий."]},
            )

    campaign = DiscoveryCampaign.objects.create(
        name=command.name,
        created_by=actor,
        search_area=search_area,
    )
    CampaignSource.objects.bulk_create(
        [CampaignSource(campaign=campaign, source=sources[source_id]) for source_id in source_ids]
    )
    CampaignCategory.objects.bulk_create(
        [
            CampaignCategory(campaign=campaign, category=categories[category_id])
            for category_id in category_ids
        ]
    )
    return campaign


@transaction.atomic
def start_campaign(
    *,
    campaign_id: UUID,
    actor: AbstractBaseUser,
    enqueue: Enqueue,
) -> DiscoveryCampaign:
    campaign = DiscoveryCampaign.objects.select_for_update().get(id=campaign_id)
    if campaign.created_by_id != actor.pk:
        raise CampaignValidationError(
            "CAMPAIGN_NOT_FOUND",
            "Кампания не найдена.",
        )
    if campaign.status != DiscoveryCampaign.Status.DRAFT:
        raise CampaignValidationError(
            "CAMPAIGN_NOT_DRAFT",
            "Запустить можно только черновик кампании.",
        )

    selections = list(
        CampaignSource.objects.filter(campaign=campaign, is_enabled=True)
        .select_related("source")
        .order_by("priority", "created_at", "id")
    )
    if not selections:
        raise CampaignValidationError(
            "NO_SOURCES_SELECTED",
            "Выберите хотя бы один источник.",
            {"source_ids": ["Выберите хотя бы один источник."]},
        )
    category_ids = tuple(campaign.categories.values_list("id", flat=True))
    for selection in selections:
        if not resolve_external_categories(selection.source_id, category_ids):
            raise CampaignValidationError(
                "SOURCE_HAS_NO_ACTIVE_MAPPINGS",
                "Для источника нет активных сопоставлений категорий.",
                {"source_ids": ["Для источника нет активных сопоставлений категорий."]},
            )

    CampaignSourceRun.objects.bulk_create(
        [CampaignSourceRun(campaign=campaign, source=selection.source) for selection in selections]
    )
    campaign.status = DiscoveryCampaign.Status.QUEUED
    campaign.total_jobs = len(selections)
    campaign.save(update_fields=("status", "total_jobs", "updated_at"))

    def log_and_enqueue() -> None:
        structured_event(
            "campaign.queued",
            campaign_id=campaign.id,
            correlation_id=str(campaign.id),
            message="Campaign queued",
        )
        enqueue(campaign.id)

    transaction.on_commit(log_and_enqueue)
    return campaign
