from rest_framework import serializers

from apps.campaigns.domain import CampaignValidationError, CreateCampaignCommand
from apps.campaigns.models import DiscoveryCampaign
from apps.campaigns.services import create_campaign
from apps.geography.models import SearchArea
from apps.sources.models import Source
from apps.system.api.exceptions import ApiException
from apps.taxonomy.models import BusinessCategory


class SearchAreaSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = SearchArea
        fields = ("id", "name")
        read_only_fields = fields


class SourceSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Source
        fields = ("id", "code", "name")
        read_only_fields = fields


class CategorySummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessCategory
        fields = ("id", "slug", "name")
        read_only_fields = fields


class CampaignSerializer(serializers.ModelSerializer):
    search_area = SearchAreaSummarySerializer(read_only=True)
    sources = SourceSummarySerializer(many=True, read_only=True)
    categories = CategorySummarySerializer(many=True, read_only=True)
    search_area_id = serializers.UUIDField(write_only=True)
    source_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        allow_empty=True,
    )
    category_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        allow_empty=True,
    )

    class Meta:
        model = DiscoveryCampaign
        fields = (
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
            "search_area_id",
            "source_ids",
            "category_ids",
        )
        read_only_fields = (
            "id",
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
        )

    def validate(self, attrs: dict) -> dict:
        search_area_id = attrs["search_area_id"]
        source_ids = tuple(dict.fromkeys(attrs["source_ids"]))
        category_ids = tuple(dict.fromkeys(attrs["category_ids"]))

        if not SearchArea.objects.filter(id=search_area_id).exists():
            self._raise_campaign_error(
                CampaignValidationError(
                    "SEARCH_AREA_NOT_FOUND",
                    "Область поиска не найдена.",
                    {"search_area_id": ["Область поиска не найдена."]},
                )
            )
        if len(Source.objects.in_bulk(source_ids)) != len(source_ids):
            self._raise_campaign_error(
                CampaignValidationError(
                    "SOURCE_NOT_FOUND",
                    "Один или несколько источников не найдены.",
                    {"source_ids": ["Один или несколько источников не найдены."]},
                )
            )
        if len(BusinessCategory.objects.in_bulk(category_ids)) != len(category_ids):
            self._raise_campaign_error(
                CampaignValidationError(
                    "CATEGORY_NOT_FOUND",
                    "Одна или несколько категорий не найдены.",
                    {"category_ids": ["Одна или несколько категорий не найдены."]},
                )
            )

        attrs["source_ids"] = source_ids
        attrs["category_ids"] = category_ids
        return attrs

    def create(self, validated_data: dict) -> DiscoveryCampaign:
        command = CreateCampaignCommand(
            name=validated_data["name"],
            search_area_id=validated_data["search_area_id"],
            source_ids=validated_data["source_ids"],
            category_ids=validated_data["category_ids"],
        )
        try:
            return create_campaign(actor=self.context["request"].user, command=command)
        except CampaignValidationError as error:
            self._raise_campaign_error(error)

    @staticmethod
    def _raise_campaign_error(error: CampaignValidationError) -> None:
        raise ApiException(
            error.code,
            error.detail,
            fields=error.fields,
        ) from error
