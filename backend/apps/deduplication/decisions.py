import logging
from uuid import UUID

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.businesses.models import Business, BusinessSourceMembership, DuplicateCandidate
from apps.deduplication.exceptions import DuplicateCandidateNotPending
from apps.deduplication.locks import owner_resolution_lock
from apps.deduplication.materialization import rebuild_business

logger = logging.getLogger(__name__)


@transaction.atomic
def confirm_duplicate(*, candidate_id: UUID, actor: User) -> DuplicateCandidate:
    """Merge an owned pending pair without deleting canonical or source history."""
    with owner_resolution_lock(actor.pk):
        candidate, businesses = _locked_pending_pair(candidate_id=candidate_id, actor=actor)
        counts = dict(
            BusinessSourceMembership.objects.filter(business_id__in=[row.id for row in businesses])
            .values("business_id")
            .annotate(total=Count("id"))
            .values_list("business_id", "total")
        )
        survivor, loser = sorted(
            businesses,
            key=lambda row: (-counts.get(row.id, 0), row.created_at, str(row.id)),
        )
        moved_memberships = BusinessSourceMembership.objects.filter(business=loser)
        moved_ids = []
        for membership in moved_memberships.select_related(
            "normalized_record__source_record__campaign"
        ):
            membership.business = survivor
            membership.full_clean()
            moved_ids.append(str(membership.id))
        candidate.moved_membership_ids = sorted(moved_ids)
        moved_memberships.update(business=survivor)
        loser.merged_into = survivor
        loser.full_clean()
        loser.save(update_fields=("merged_into", "updated_at"))
        rebuild_business(business_id=survivor.id)

        candidate.survivor_business = survivor
        candidate.merged_business = loser
        _save_decision(candidate, actor=actor, status=DuplicateCandidate.Status.CONFIRMED)
        pending = (
            DuplicateCandidate.objects.select_for_update()
            .filter(owner=actor, status=DuplicateCandidate.Status.PENDING)
            .filter(Q(left_business=loser) | Q(right_business=loser))
            .order_by("id")
        )
        for incompatible in pending:
            incompatible.status = DuplicateCandidate.Status.SUPERSEDED
            incompatible.full_clean()
            incompatible.save(update_fields=("status", "updated_at"))
        return candidate


@transaction.atomic
def reject_duplicate(*, candidate_id: UUID, actor: User) -> DuplicateCandidate:
    """Record an owned rejection while preserving businesses and memberships."""
    with owner_resolution_lock(actor.pk):
        candidate, _ = _locked_pending_pair(candidate_id=candidate_id, actor=actor)
        _save_decision(candidate, actor=actor, status=DuplicateCandidate.Status.REJECTED)
        return candidate


def _locked_pending_pair(
    *, candidate_id: UUID, actor: User
) -> tuple[DuplicateCandidate, list[Business]]:
    candidate = DuplicateCandidate.objects.select_for_update().get(id=candidate_id, owner=actor)
    if candidate.status != DuplicateCandidate.Status.PENDING:
        raise DuplicateCandidateNotPending
    businesses = list(
        Business.objects.select_for_update()
        .filter(id__in=(candidate.left_business_id, candidate.right_business_id))
        .order_by("id")
    )
    if any(business.merged_into_id is not None for business in businesses):
        raise DuplicateCandidateNotPending
    # Check all pair ownership invariants before moving any memberships.
    candidate.full_clean()
    return candidate, businesses


def _save_decision(candidate: DuplicateCandidate, *, actor: User, status: str) -> None:
    candidate.status = status
    candidate.decided_by = actor
    candidate.decided_at = timezone.now()
    candidate.full_clean()
    candidate.save()
    # Freeze the minimal event payload now; only emit after the outermost commit.
    payload = {
        "candidate_id": str(candidate.id),
        "owner_id": candidate.owner_id,
        "actor_id": actor.pk,
        "left_business_id": str(candidate.left_business_id),
        "right_business_id": str(candidate.right_business_id),
        "survivor_business_id": (
            str(candidate.survivor_business_id) if candidate.survivor_business_id else None
        ),
        "merged_business_id": (
            str(candidate.merged_business_id) if candidate.merged_business_id else None
        ),
        "score": candidate.score,
        "resolution_version": candidate.resolution_version,
        "decision": status,
    }
    transaction.on_commit(
        lambda: logger.info("duplicate_candidate.decided", extra={"decision_payload": payload})
    )
