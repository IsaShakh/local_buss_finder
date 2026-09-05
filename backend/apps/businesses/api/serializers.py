import json

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers

from apps.sources.models import NormalizedSourceRecord, Source, SourceRecord


class SourceSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Source
        fields = ("code", "name")
        read_only_fields = fields


def _category_summary(category):
    if category is None:
        return None
    return {"id": category.id, "name": category.name, "slug": category.slug}


def _district_summary(district):
    if district is None:
        return None
    return {"id": district.id, "name": district.name_ru, "slug": district.slug}


def _country_summary(country):
    if country is None:
        return None
    return {"id": country.id, "name": country.name_ru, "code": country.code}


def _province_summary(province):
    if province is None:
        return None
    return {"id": province.id, "name": province.name_ru, "code": province.code}


def _neighborhood_summary(neighborhood):
    if neighborhood is None:
        return None
    return {"id": neighborhood.id, "name": neighborhood.name_ru, "slug": neighborhood.slug}


def _point_geojson(point):
    return None if point is None else json.loads(point.geojson)


class SourceRecordListSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="source_record_id", read_only=True)
    source = SourceSummarySerializer(source="source_record.source", read_only=True)
    category = serializers.SerializerMethodField()
    district = serializers.SerializerMethodField()
    normalization_status = serializers.SerializerMethodField()
    fetched_at = serializers.DateTimeField(source="source_record.fetched_at", read_only=True)
    is_canonical = serializers.SerializerMethodField()

    class Meta:
        model = NormalizedSourceRecord
        fields = (
            "id",
            "display_name",
            "source",
            "category",
            "district",
            "phones",
            "websites",
            "normalization_status",
            "fetched_at",
            "is_canonical",
        )
        read_only_fields = fields

    def get_category(self, obj):
        return _category_summary(obj.category)

    def get_district(self, obj):
        return _district_summary(obj.district)

    def get_normalization_status(self, obj):
        return SourceRecord.NormalizationStatus.NORMALIZED

    def get_is_canonical(self, obj):
        return False


class NormalizedSourceRecordDetailSerializer(serializers.ModelSerializer):
    category = serializers.SerializerMethodField()
    country = serializers.SerializerMethodField()
    province = serializers.SerializerMethodField()
    district = serializers.SerializerMethodField()
    neighborhood = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()

    class Meta:
        model = NormalizedSourceRecord
        fields = (
            "display_name",
            "normalized_name",
            "match_name",
            "category",
            "address_text",
            "country",
            "province",
            "district",
            "neighborhood",
            "location",
            "phones",
            "emails",
            "websites",
            "social_urls",
            "attributes",
            "warnings",
            "normalization_version",
            "normalized_at",
        )
        read_only_fields = fields

    def get_category(self, obj):
        return _category_summary(obj.category)

    def get_country(self, obj):
        return _country_summary(obj.country)

    def get_province(self, obj):
        return _province_summary(obj.province)

    def get_district(self, obj):
        return _district_summary(obj.district)

    def get_neighborhood(self, obj):
        return _neighborhood_summary(obj.neighborhood)

    def get_location(self, obj):
        return _point_geojson(obj.location)


class SourceRecordDetailSerializer(serializers.ModelSerializer):
    is_canonical = serializers.SerializerMethodField()
    source = SourceSummarySerializer(read_only=True)
    raw = serializers.SerializerMethodField()
    payload = serializers.SerializerMethodField()
    normalized = serializers.SerializerMethodField()

    class Meta:
        model = SourceRecord
        fields = (
            "id",
            "is_canonical",
            "campaign_id",
            "source_run_id",
            "source",
            "external_id",
            "source_dataset_version",
            "source_url",
            "attribution",
            "license_code",
            "raw",
            "payload",
            "normalization_status",
            "normalization_error_code",
            "parser_error_code",
            "fetched_at",
            "normalized",
        )
        read_only_fields = fields

    def get_is_canonical(self, obj):
        return False

    def get_raw(self, obj):
        return {
            "name": obj.raw_name,
            "category": obj.raw_category,
            "address": obj.raw_address,
            "phones": obj.raw_phones,
            "emails": obj.raw_emails,
            "websites": obj.raw_websites,
            "social_urls": obj.raw_social_urls,
            "location": _point_geojson(obj.raw_location),
        }

    def get_payload(self, obj):
        return {
            "key": obj.raw_payload_key,
            "sha256": obj.raw_payload_sha256,
            "bytes": obj.raw_payload_bytes,
            "schema_version": obj.payload_schema_version,
        }

    def get_normalized(self, obj):
        try:
            normalized = obj.normalized_record
        except ObjectDoesNotExist:
            return None
        return NormalizedSourceRecordDetailSerializer(normalized).data


class SourceRecordQuerySerializer(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, required=False)
    page_size = serializers.IntegerField(min_value=1, max_value=100, required=False)
    campaign = serializers.UUIDField(required=False)
    source = serializers.SlugField(required=False)
    category = serializers.SlugField(required=False)
    search = serializers.CharField(required=False, allow_blank=False, trim_whitespace=True)
    ordering = serializers.ChoiceField(
        choices=("display_name", "fetched_at", "-fetched_at"),
        required=False,
    )

    def to_internal_value(self, data):
        unknown = set(data.keys()).difference(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {key: ["Неизвестный параметр запроса."] for key in sorted(unknown)}
            )
        return super().to_internal_value(data)


class RecentCampaignSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    normalized = serializers.IntegerField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class DashboardRecordsSerializer(serializers.Serializer):
    raw = serializers.IntegerField(read_only=True)
    normalized = serializers.IntegerField(read_only=True)
    rejected = serializers.IntegerField(read_only=True)
    failed = serializers.IntegerField(read_only=True)


class DashboardCampaignsSerializer(serializers.Serializer):
    total = serializers.IntegerField(read_only=True)
    running = serializers.IntegerField(read_only=True)
    with_errors = serializers.IntegerField(read_only=True)


class DashboardSummarySerializer(serializers.Serializer):
    records = DashboardRecordsSerializer(read_only=True)
    campaigns = DashboardCampaignsSerializer(read_only=True)
    recent_campaigns = RecentCampaignSerializer(many=True, read_only=True)
