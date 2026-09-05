from collections import defaultdict
from collections.abc import Iterable, Mapping
from uuid import UUID

from django.core.exceptions import ValidationError

from apps.businesses.models import Business, BusinessSourceMembership
from apps.deduplication.identity import extract_official_domains
from apps.normalization.rules.emails import normalize_emails
from apps.normalization.rules.phones import InvalidPhoneNumber, normalize_phone
from apps.normalization.rules.socials import normalize_social_urls
from apps.normalization.rules.urls import InvalidUrl, normalize_url
from apps.sources.models import NormalizedSourceRecord


def completeness_score(record: NormalizedSourceRecord) -> int:
    """Count the eight approved groups used to choose a canonical primary row."""
    return sum(
        (
            bool(record.display_name.strip()),
            record.category_id is not None,
            bool(record.address_text.strip()),
            record.location is not None,
            bool(record.phones),
            bool(record.emails),
            bool(record.websites),
            any(record.social_urls.values()),
        )
    )


def select_primary_record(records: Iterable[NormalizedSourceRecord]) -> NormalizedSourceRecord:
    """Return the stable canonical primary record from normalized source data."""
    try:
        return min(records, key=_primary_sort_key)
    except ValueError as error:
        raise ValueError("A business requires at least one normalized record.") from error


def seed_business(*, normalized_record: NormalizedSourceRecord, owner_id: UUID) -> Business:
    """Create an active owner-scoped business and materialize its seed membership."""
    normalized_record_owner_id = (
        NormalizedSourceRecord.objects.filter(id=normalized_record.id)
        .values_list("source_record__campaign__created_by_id", flat=True)
        .get()
    )
    if normalized_record_owner_id != owner_id:
        raise ValidationError(
            {"normalized_record": "Business and normalized record must have the same owner."}
        )

    business = Business.objects.create(owner_id=owner_id)
    BusinessSourceMembership.objects.create(
        business=business,
        normalized_record=normalized_record,
        match_kind=BusinessSourceMembership.MatchKind.SEED,
    )
    return rebuild_business(business_id=business.id)


def rebuild_business(*, business_id: UUID) -> Business:
    """Recompute every canonical field from a business's active memberships."""
    business = Business.objects.get(id=business_id)
    if business.merged_into_id is not None:
        raise ValueError("Cannot rebuild a merged business.")

    records = [
        membership.normalized_record
        for membership in BusinessSourceMembership.objects.filter(business_id=business.id).select_related(
            "normalized_record",
            "normalized_record__source_record",
            "normalized_record__source_record__source",
        )
    ]
    primary = select_primary_record(records)
    websites = _normalized_websites(records)

    business.primary_normalized_record_id = primary.id
    business.display_name = primary.display_name
    business.normalized_name = primary.normalized_name
    business.match_name = primary.match_name
    business.category_id = primary.category_id
    business.address_text = primary.address_text
    business.country_id = primary.country_id
    business.province_id = primary.province_id
    business.district_id = primary.district_id
    business.neighborhood_id = primary.neighborhood_id
    business.location = primary.location
    business.phones = _normalized_phones(records)
    business.emails = _normalized_emails(records)
    business.websites = websites
    business.domains = list(extract_official_domains(websites))
    business.social_urls = _normalized_social_urls(records)
    fetched_at = [record.source_record.fetched_at for record in records]
    business.first_seen_at = min(fetched_at)
    business.last_seen_at = max(fetched_at)
    business.full_clean()
    business.save(
        update_fields=(
            "primary_normalized_record",
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
            "domains",
            "social_urls",
            "first_seen_at",
            "last_seen_at",
            "updated_at",
        )
    )
    return business


def _primary_sort_key(record: NormalizedSourceRecord) -> tuple[int, float, str, str]:
    return (
        -completeness_score(record),
        -record.source_record.fetched_at.timestamp(),
        record.source_record.source.code,
        str(record.id),
    )


def _normalized_phones(records: Iterable[NormalizedSourceRecord]) -> list[str]:
    phones = set()
    for record in records:
        for value in record.phones:
            try:
                phones.add(normalize_phone(value, default_region="TR"))
            except InvalidPhoneNumber:
                continue
    return sorted(phones)


def _normalized_emails(records: Iterable[NormalizedSourceRecord]) -> list[str]:
    return sorted(
        {
            email
            for record in records
            for email in normalize_emails(record.emails).values
        }
    )


def _normalized_websites(records: Iterable[NormalizedSourceRecord]) -> list[str]:
    websites = set()
    for record in records:
        for value in record.websites:
            try:
                websites.add(normalize_url(value))
            except InvalidUrl:
                continue
    return sorted(websites)


def _normalized_social_urls(records: Iterable[NormalizedSourceRecord]) -> dict[str, list[str]]:
    providers: defaultdict[str, set[str]] = defaultdict(set)
    for record in records:
        for provider, urls in _social_mapping(record.social_urls).items():
            providers[provider].update(urls)
    return {provider: sorted(providers[provider]) for provider in sorted(providers)}


def _social_mapping(values: Mapping[str, object]) -> dict[str, tuple[str, ...]]:
    return normalize_social_urls(
        {
            provider: raw_urls
            for provider, raw_urls in values.items()
            if isinstance(provider, str) and isinstance(raw_urls, list)
        }
    )
