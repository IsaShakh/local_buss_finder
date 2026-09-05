import json

from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse
from django.utils.translation import gettext as _
from rest_framework import serializers

from apps.businesses.models import Business, BusinessSourceMembership, DuplicateCandidate
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


class DashboardBusinessesSerializer(serializers.Serializer):
    active = serializers.IntegerField(read_only=True)
    pending_duplicates = serializers.IntegerField(read_only=True)


class DashboardSummarySerializer(serializers.Serializer):
    records = DashboardRecordsSerializer(read_only=True)
    campaigns = DashboardCampaignsSerializer(read_only=True)
    recent_campaigns = RecentCampaignSerializer(many=True, read_only=True)
    businesses = DashboardBusinessesSerializer(read_only=True)


class StrictInputSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("Ожидается объект.")
        invalid = set(data).difference(self.fields)
        if hasattr(data, "getlist"):
            invalid.update(key for key in data if len(data.getlist(key)) != 1)
        if invalid:
            raise serializers.ValidationError(
                {key: ["Неизвестный или повторный параметр."] for key in sorted(invalid)}
            )
        # DRF treats empty optional HTML form values as absent. Query parameters
        # are an API contract: explicitly supplied blanks must be validated.
        return super().to_internal_value({key: data[key] for key in data})


class PaginationQuerySerializer(StrictInputSerializer):
    page = serializers.IntegerField(min_value=1, required=False)
    page_size = serializers.IntegerField(min_value=1, max_value=100, required=False)


class BusinessQuerySerializer(PaginationQuerySerializer):
    campaign = serializers.UUIDField(required=False)
    source = serializers.SlugField(required=False)
    category = serializers.SlugField(required=False)
    search = serializers.CharField(required=False, allow_blank=False, trim_whitespace=True)
    ordering = serializers.ChoiceField(
        choices=(
            "display_name",
            "first_seen_at",
            "-first_seen_at",
            "last_seen_at",
            "-last_seen_at",
            "updated_at",
            "-updated_at",
        ),
        required=False,
    )


class BusinessListSerializer(serializers.ModelSerializer):
    category = serializers.SerializerMethodField()
    district = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()
    source_count = serializers.IntegerField(read_only=True)
    source_record_count = serializers.IntegerField(read_only=True)
    pending_duplicate_count = serializers.IntegerField(read_only=True)
    is_canonical = serializers.SerializerMethodField()

    class Meta:
        model = Business
        fields = (
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
        )
        read_only_fields = fields

    def get_category(self, obj):
        return _category_summary(obj.category)

    def get_district(self, obj):
        return _district_summary(obj.district)

    def get_location(self, obj):
        return _point_geojson(obj.location)

    def get_is_canonical(self, obj):
        return True


class BusinessMembershipSerializer(serializers.ModelSerializer):
    source = SourceSummarySerializer(
        source="normalized_record.source_record.source", read_only=True
    )
    external_id = serializers.CharField(source="normalized_record.source_record.external_id")
    campaign_id = serializers.UUIDField(source="normalized_record.source_record.campaign_id")
    fetched_at = serializers.DateTimeField(source="normalized_record.source_record.fetched_at")
    source_dataset_version = serializers.CharField(
        source="normalized_record.source_record.source_dataset_version"
    )
    source_record_id = serializers.UUIDField(source="normalized_record.source_record_id")
    source_record_url = serializers.SerializerMethodField()

    class Meta:
        model = BusinessSourceMembership
        fields = (
            "id",
            "source",
            "external_id",
            "campaign_id",
            "fetched_at",
            "source_dataset_version",
            "match_kind",
            "match_score",
            "source_record_id",
            "source_record_url",
        )
        read_only_fields = fields

    def get_source_record_url(self, obj):
        return reverse(
            "source-record-detail", kwargs={"pk": obj.normalized_record.source_record_id}
        )


class BusinessDetailSerializer(BusinessListSerializer):
    country = serializers.SerializerMethodField()
    province = serializers.SerializerMethodField()
    neighborhood = serializers.SerializerMethodField()
    memberships = BusinessMembershipSerializer(source="api_memberships", many=True, read_only=True)
    memberships_truncated = serializers.BooleanField(read_only=True)

    class Meta(BusinessListSerializer.Meta):
        fields = (
            *BusinessListSerializer.Meta.fields,
            "country",
            "province",
            "neighborhood",
            "memberships",
            "memberships_truncated",
        )
        read_only_fields = fields

    def get_country(self, obj):
        return _country_summary(obj.country)

    def get_province(self, obj):
        return _province_summary(obj.province)

    def get_neighborhood(self, obj):
        return _neighborhood_summary(obj.neighborhood)


SIGNAL_LABELS = {
    "source_identity": "Совпадает идентификатор источника",
    "exact_phone": "Совпадает телефон",
    "exact_domain": "Совпадает домен",
    "exact_name": "Совпадает название",
    "name_similarity_90": "Сходство названий от 90%",
    "name_similarity_78": "Сходство названий от 78%",
    "name_similarity_65": "Сходство названий от 65%",
    "exact_address": "Совпадает адрес",
    "address_similarity_80": "Сходство адресов от 80%",
    "distance_25m": "Расстояние до 25 м",
    "distance_75m": "Расстояние до 75 м",
    "distance_250m": "Расстояние до 250 м",
    "distance_500m": "Расстояние до 500 м",
    "same_category": "Совпадает категория",
    "incompatible_category": "Разные категории",
}


class DuplicateCandidateSerializer(serializers.ModelSerializer):
    left_business = BusinessListSerializer(read_only=True)
    right_business = BusinessListSerializer(read_only=True)
    signals = serializers.SerializerMethodField()

    class Meta:
        model = DuplicateCandidate
        fields = (
            "id",
            "left_business",
            "right_business",
            "score",
            "signals",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_signals(self, obj):
        return [
            {
                "code": signal["code"],
                "weight": signal["weight"],
                "value": signal.get("value"),
                "label": _(SIGNAL_LABELS.get(signal["code"], "Неизвестный сигнал")),
            }
            for signal in obj.signals
        ]


class DuplicateDecisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DuplicateCandidate
        fields = ("id", "status", "survivor_business_id", "merged_business_id")
        read_only_fields = fields
