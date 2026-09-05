from dataclasses import asdict, dataclass
from typing import Literal
from uuid import UUID

from django.db import transaction

from apps.businesses.models import BusinessSourceMembership, DuplicateCandidate
from apps.deduplication.candidates import CandidateMatch, find_candidate_businesses
from apps.deduplication.locks import owner_resolution_lock
from apps.deduplication.materialization import rebuild_business, seed_business
from apps.deduplication.scoring import CANDIDATE_SCORE_THRESHOLD, RESOLUTION_VERSION
from apps.sources.models import NormalizedSourceRecord
from common.observability import structured_event


@dataclass(frozen=True)
class ResolutionOutcome:
    business_id: UUID
    membership_id: UUID
    action: Literal["seeded", "source_identity", "automatic", "already_resolved"]
    candidate_ids: tuple[UUID, ...]


@transaction.atomic
def resolve_normalized_record(normalized_record_id: UUID) -> ResolutionOutcome:
    record = NormalizedSourceRecord.objects.select_related("source_record__campaign").get(
        id=normalized_record_id
    )
    owner_id = record.source_record.campaign.created_by_id
    with owner_resolution_lock(owner_id):
        existing = BusinessSourceMembership.objects.filter(normalized_record_id=record.id).first()
        if existing is not None:
            return ResolutionOutcome(existing.business_id, existing.id, "already_resolved", ())

        matches = find_candidate_businesses(normalized_record=record)
        winner = next((match for match in matches if match.assessment.automatic), None)
        if winner is None:
            business = seed_business(normalized_record=record, owner_id=owner_id)
            membership = BusinessSourceMembership.objects.get(normalized_record_id=record.id)
            action = "seeded"
        else:
            action = "source_identity" if winner.facts.source_identity else "automatic"
            membership = BusinessSourceMembership(
                business_id=winner.business_id,
                normalized_record=record,
                match_kind=action,
                match_score=winner.assessment.score,
                match_signals=[asdict(signal) for signal in winner.assessment.signals],
                resolution_version=RESOLUTION_VERSION,
            )
            membership.full_clean()
            membership.save()
            business = membership.business

        candidate_ids = []
        for match in matches:
            if (
                match.business_id == business.id
                or match.assessment.score < CANDIDATE_SCORE_THRESHOLD
            ):
                continue
            candidate = _pending_candidate(owner_id=owner_id, business_id=business.id, match=match)
            if candidate is not None:
                candidate_ids.append(candidate.id)
        if winner is not None:
            rebuild_business(business_id=business.id)
        # Seed materialization already rebuilds; both paths share that public policy.
        outcome = ResolutionOutcome(business.id, membership.id, action, tuple(candidate_ids))
        transaction.on_commit(
            lambda: structured_event(
                f"business.resolution.{action}",
                campaign_id=record.source_record.campaign_id,
                source_run_id=record.source_record.source_run_id,
                source_record_id=record.source_record_id,
                correlation_id=str(record.source_record.campaign_id),
                message="Normalized source record resolved",
            )
        )
        return outcome


def _pending_candidate(
    *, owner_id: UUID | int, business_id: UUID, match: CandidateMatch
) -> DuplicateCandidate | None:
    left_id, right_id = DuplicateCandidate.ordered_pair(business_id, match.business_id)
    candidate = DuplicateCandidate.objects.filter(
        owner_id=owner_id,
        left_business_id=left_id,
        right_business_id=right_id,
    ).first()
    if candidate is not None and candidate.status != DuplicateCandidate.Status.PENDING:
        return None
    if candidate is None:
        candidate = DuplicateCandidate(
            owner_id=owner_id,
            left_business_id=left_id,
            right_business_id=right_id,
        )
    candidate.score = match.assessment.score
    candidate.signals = [asdict(signal) for signal in match.assessment.signals]
    candidate.resolution_version = RESOLUTION_VERSION
    # Explicit validated upsert under the owner lock: update_or_create saves
    # without model validation and can accidentally overwrite terminal status.
    candidate.full_clean()
    candidate.save()
    return candidate
