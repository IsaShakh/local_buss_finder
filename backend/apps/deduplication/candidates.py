from dataclasses import dataclass
from math import cos, radians
from uuid import UUID

from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point, Polygon
from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import FloatField, Q, Value

from apps.businesses.models import Business
from apps.deduplication.domain import MatchAssessment, MatchFacts
from apps.deduplication.identity import extract_official_domains
from apps.deduplication.scoring import assess_match, category_relation
from apps.sources.models import NormalizedSourceRecord

SPATIAL_RADIUS_M = 500
SPATIAL_NAME_THRESHOLD = 0.55
SPATIAL_CANDIDATE_LIMIT = 50


@dataclass(frozen=True)
class CandidateMatch:
    business_id: UUID
    facts: MatchFacts
    assessment: MatchAssessment


def find_candidate_businesses(*, normalized_record: NormalizedSourceRecord) -> list[CandidateMatch]:
    """Union indexed branches, bounding only the spatial branch before scoring."""
    record = normalized_record
    source_record = record.source_record
    businesses = Business.active.filter(owner_id=source_record.campaign.created_by_id).order_by()
    identity_ids = set(
        businesses.filter(
            memberships__normalized_record__source_record__source_id=source_record.source_id,
            memberships__normalized_record__source_record__external_id=source_record.external_id,
        ).values_list("id", flat=True)
    )
    ids = set(identity_ids)
    phones = set(record.phones)
    domains = set(extract_official_domains(record.websites))
    contact_query = Q()
    for phone in sorted(phones):
        contact_query |= Q(phones__contains=[phone])
    for domain in sorted(domains):
        contact_query |= Q(domains__contains=[domain])
    if contact_query:
        ids.update(businesses.filter(contact_query).values_list("id", flat=True))

    if record.location is not None and record.match_name:
        spatial = (
            businesses.filter(_spatial_envelopes(record.location))
            .annotate(
                candidate_name_similarity=TrigramSimilarity("match_name", record.match_name),
                candidate_distance=Distance("location", record.location, spheroid=True),
            )
            .filter(
                candidate_name_similarity__gte=SPATIAL_NAME_THRESHOLD,
                candidate_distance__lte=SPATIAL_RADIUS_M,
            )
            .order_by("-candidate_name_similarity", "candidate_distance", "id")
        )
        ids.update(spatial.values_list("id", flat=True)[:SPATIAL_CANDIDATE_LIMIT])

    if not ids:
        return []
    candidates = businesses.filter(id__in=ids).annotate(
        candidate_name_similarity=TrigramSimilarity("match_name", record.match_name),
        candidate_address_similarity=TrigramSimilarity("address_text", record.address_text),
        candidate_distance=(
            Distance("location", record.location, spheroid=True)
            if record.location is not None
            else Value(None, output_field=FloatField())
        ),
    )
    matches = []
    for business in candidates:
        facts = MatchFacts(
            source_identity=business.id in identity_ids,
            phone_match=bool(phones.intersection(business.phones)),
            domain_match=bool(domains.intersection(business.domains)),
            exact_name=bool(record.match_name and record.match_name == business.match_name),
            name_similarity=business.candidate_name_similarity,
            exact_address=bool(
                record.address_text and record.address_text == business.address_text
            ),
            address_similarity=business.candidate_address_similarity,
            distance_m=(
                business.candidate_distance.m if business.candidate_distance is not None else None
            ),
            category_relation=category_relation(record.category_id, business.category_id),
        )
        matches.append(CandidateMatch(business.id, facts, assess_match(facts)))
    return sorted(matches, key=lambda match: (-match.assessment.score, str(match.business_id)))


def _spatial_envelopes(point: Point) -> Q:
    # A conservative WGS84 envelope keeps the geometry GiST index usable. Exact
    # spheroidal metres are checked afterwards. 110 km is below a degree's
    # minimum meridional length; use the most poleward latitude for longitude.
    latitude_delta = SPATIAL_RADIUS_M / 110_000
    poleward = min(90, abs(point.y) + latitude_delta)
    longitude_delta = 180 if poleward == 90 else min(180, latitude_delta / cos(radians(poleward)))
    query = Q()
    # Shifted envelopes include neighbours across the antimeridian.
    for shift in (-360, 0, 360):
        envelope = Polygon.from_bbox(
            (
                point.x - longitude_delta + shift,
                max(-90, point.y - latitude_delta),
                point.x + longitude_delta + shift,
                min(90, point.y + latitude_delta),
            )
        )
        envelope.srid = 4326
        query |= Q(location__bboverlaps=envelope)
    return query
