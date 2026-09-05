from collections.abc import Callable, Iterable
from dataclasses import replace
from uuid import UUID

from django.contrib.gis.geos import Point
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.campaigns.models import CampaignSourceRun, DiscoveryCampaign
from apps.discovery.domain import RawBusinessRecord
from apps.geography.models import SearchArea
from apps.sources.models import NormalizedSourceRecord, SourceRecord
from apps.taxonomy.services import resolve_category

from .domain import NormalizationResult, NormalizedBusinessData, NormalizedStrings
from .rules.addresses import normalize_address
from .rules.coordinates import InvalidCoordinates, normalize_coordinates
from .rules.emails import normalize_emails
from .rules.names import MissingName, normalize_name
from .rules.phones import InvalidPhoneNumber, normalize_phone
from .rules.socials import normalize_social_urls
from .rules.urls import InvalidUrl, normalize_url


def _normalize_values(
    values: Iterable[str],
    normalizer: Callable[[str], str],
    *,
    warning: str,
    invalid_error: type[ValueError],
) -> NormalizedStrings:
    normalized: list[str] = []
    warnings: list[str] = []
    for value in values:
        try:
            result = normalizer(value)
        except invalid_error:
            if warning not in warnings:
                warnings.append(warning)
            continue
        if result not in normalized:
            normalized.append(result)
    return NormalizedStrings(tuple(normalized), tuple(warnings))


def _social_url_warnings(raw: RawBusinessRecord) -> tuple[str, ...]:
    for urls in raw.raw_social_urls.values():
        for value in urls:
            try:
                normalize_url(value)
            except InvalidUrl:
                return ("INVALID_URL",)
    return ()


def normalize_business_record(
    raw: RawBusinessRecord,
    *,
    category_id: UUID | None,
) -> NormalizationResult:
    try:
        names = normalize_name(raw.raw_name or "")
    except MissingName:
        return NormalizationResult(status="rejected", data=None, error_code="MISSING_NAME")

    phones = _normalize_values(
        raw.raw_phones,
        lambda value: normalize_phone(value, default_region="TR"),
        warning="INVALID_PHONE",
        invalid_error=InvalidPhoneNumber,
    )
    emails = normalize_emails(raw.raw_emails)
    websites = _normalize_values(
        raw.raw_websites,
        normalize_url,
        warning="INVALID_URL",
        invalid_error=InvalidUrl,
    )

    coordinate_warnings: tuple[str, ...] = ()
    location = None
    if raw.longitude is None and raw.latitude is None:
        coordinate_warnings = ("MISSING_COORDINATES",)
    elif raw.longitude is None or raw.latitude is None:
        coordinate_warnings = ("INVALID_COORDINATES",)
    else:
        try:
            location = normalize_coordinates(raw.longitude, raw.latitude)
        except InvalidCoordinates:
            coordinate_warnings = ("INVALID_COORDINATES",)

    category_warnings = () if category_id is not None else ("UNKNOWN_CATEGORY",)
    social_url_warnings = _social_url_warnings(raw)
    warnings = tuple(
        dict.fromkeys(
            phones.warnings
            + emails.warnings
            + websites.warnings
            + social_url_warnings
            + coordinate_warnings
            + category_warnings
        )
    )
    return NormalizationResult(
        status="normalized",
        data=NormalizedBusinessData(
            display_name=names.display_name,
            normalized_name=names.normalized_name,
            match_name=names.match_name,
            category_id=category_id,
            address_text=normalize_address(raw.raw_address),
            location=location,
            phones=phones.values,
            emails=emails.values,
            websites=websites.values,
            social_urls=normalize_social_urls(raw.raw_social_urls),
            warnings=warnings,
            attributes={},
        ),
        error_code=None,
    )


def _raw_business_record(source_record: SourceRecord) -> RawBusinessRecord:
    location = source_record.raw_location
    return RawBusinessRecord(
        external_id=source_record.external_id,
        raw_name=source_record.raw_name,
        raw_category=source_record.raw_category,
        raw_address=source_record.raw_address,
        raw_phones=tuple(source_record.raw_phones),
        raw_emails=tuple(source_record.raw_emails),
        raw_websites=tuple(source_record.raw_websites),
        raw_social_urls={
            provider: tuple(urls) for provider, urls in source_record.raw_social_urls.items()
        },
        longitude=None if location is None else location.x,
        latitude=None if location is None else location.y,
    )


def _record_rejection_once(
    *,
    source_record: SourceRecord,
    source_run: CampaignSourceRun,
    campaign: DiscoveryCampaign,
    error_code: str,
) -> None:
    first_outcome = source_record.normalization_status == SourceRecord.NormalizationStatus.PENDING
    SourceRecord.objects.filter(id=source_record.id).update(
        normalization_status=SourceRecord.NormalizationStatus.REJECTED,
        normalization_error_code=error_code,
        updated_at=timezone.now(),
    )
    if first_outcome:
        CampaignSourceRun.objects.filter(id=source_run.id).update(
            rejected_records=F("rejected_records") + 1,
            updated_at=timezone.now(),
        )
        DiscoveryCampaign.objects.filter(id=campaign.id).update(
            rejected_records=F("rejected_records") + 1,
            updated_at=timezone.now(),
        )


def _materialize_result(
    *,
    source_record: SourceRecord,
    source_run: CampaignSourceRun,
    campaign: DiscoveryCampaign,
    search_area: SearchArea,
    result: NormalizationResult,
) -> NormalizedSourceRecord:
    if result.data is None:
        raise RuntimeError("normalized outcome requires data")
    data = replace(
        result.data,
        attributes={**result.data.attributes, "geography_basis": "search_area"},
    )
    now = timezone.now()
    location = None
    if data.location is not None:
        location = Point(data.location.longitude, data.location.latitude, srid=4326)
    normalized, _ = NormalizedSourceRecord.objects.update_or_create(
        source_record=source_record,
        defaults={
            "display_name": data.display_name,
            "normalized_name": data.normalized_name,
            "match_name": data.match_name,
            "category_id": data.category_id,
            "address_text": data.address_text,
            "country_id": search_area.country_id,
            "province_id": search_area.province_id,
            "district_id": search_area.district_id,
            "neighborhood_id": search_area.neighborhood_id,
            "location": location,
            "phones": list(data.phones),
            "emails": list(data.emails),
            "websites": list(data.websites),
            "social_urls": {provider: list(urls) for provider, urls in data.social_urls.items()},
            "attributes": data.attributes,
            "warnings": list(data.warnings),
            "normalization_version": "tr-v1",
            "normalized_at": now,
        },
    )
    first_outcome = source_record.normalization_status == SourceRecord.NormalizationStatus.PENDING
    SourceRecord.objects.filter(id=source_record.id).update(
        normalization_status=SourceRecord.NormalizationStatus.NORMALIZED,
        normalization_error_code=None,
        updated_at=now,
    )
    if first_outcome:
        CampaignSourceRun.objects.filter(id=source_run.id).update(
            normalized_records=F("normalized_records") + 1,
            updated_at=now,
        )
        DiscoveryCampaign.objects.filter(id=campaign.id).update(
            normalized_records=F("normalized_records") + 1,
            updated_at=now,
        )
    return normalized


def materialize_normalization(source_record_id: UUID) -> NormalizedSourceRecord | None:
    with transaction.atomic():
        references = (
            SourceRecord.objects.filter(id=source_record_id)
            .values("campaign_id", "source_run_id")
            .first()
        )
        if references is None:
            return None

        campaign = DiscoveryCampaign.objects.select_for_update().get(id=references["campaign_id"])
        source_run = CampaignSourceRun.objects.select_for_update().get(
            id=references["source_run_id"]
        )
        source_record = SourceRecord.objects.select_for_update().get(id=source_record_id)

        if source_record.parser_error_code is not None:
            return None
        if source_record.normalization_status == SourceRecord.NormalizationStatus.REJECTED:
            return None

        search_area = SearchArea.objects.get(id=campaign.search_area_id)
        category_id = None
        if source_record.raw_category:
            category_id = resolve_category(source_record.source_id, source_record.raw_category)
        result = normalize_business_record(
            _raw_business_record(source_record),
            category_id=category_id,
        )
        if result.status == "rejected":
            _record_rejection_once(
                source_record=source_record,
                source_run=source_run,
                campaign=campaign,
                error_code=result.error_code or "NORMALIZATION_ERROR",
            )
            return None
        return _materialize_result(
            source_record=source_record,
            source_run=source_run,
            campaign=campaign,
            search_area=search_area,
            result=result,
        )
