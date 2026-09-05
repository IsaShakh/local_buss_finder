from uuid import UUID

from apps.deduplication.domain import MatchAssessment, MatchFacts, MatchSignal

RESOLUTION_VERSION = "deterministic-v1"

CANDIDATE_SCORE_THRESHOLD = 55
AUTOMATIC_SCORE_THRESHOLD = 80
AUTOMATIC_CONTACT_MAX_DISTANCE_M = 250
AUTOMATIC_EXACT_DETAILS_MAX_DISTANCE_M = 75

EXACT_PHONE_WEIGHT = 35
EXACT_DOMAIN_WEIGHT = 35
EXACT_NAME_WEIGHT = 30
NAME_SIMILARITY_90_WEIGHT = 25
NAME_SIMILARITY_78_WEIGHT = 18
NAME_SIMILARITY_65_WEIGHT = 10
EXACT_ADDRESS_WEIGHT = 20
ADDRESS_SIMILARITY_80_WEIGHT = 12
DISTANCE_25M_WEIGHT = 25
DISTANCE_75M_WEIGHT = 20
DISTANCE_250M_WEIGHT = 12
DISTANCE_500M_WEIGHT = 5
SAME_CATEGORY_WEIGHT = 10
INCOMPATIBLE_CATEGORY_WEIGHT = -25

NAME_SIMILARITY_90_THRESHOLD = 0.90
NAME_SIMILARITY_78_THRESHOLD = 0.78
NAME_SIMILARITY_65_THRESHOLD = 0.65
ADDRESS_SIMILARITY_80_THRESHOLD = 0.80
DISTANCE_25M_THRESHOLD = 25
DISTANCE_75M_THRESHOLD = 75
DISTANCE_250M_THRESHOLD = 250
DISTANCE_500M_THRESHOLD = 500


def category_relation(left_category_id: UUID | None, right_category_id: UUID | None) -> str:
    if left_category_id is None or right_category_id is None:
        return "neutral"
    if left_category_id == right_category_id:
        return "same"
    return "incompatible"


def assess_match(facts: MatchFacts) -> MatchAssessment:
    if facts.source_identity:
        return MatchAssessment(
            score=100,
            signals=(MatchSignal(code="source_identity", weight=100),),
            automatic=True,
        )

    signals = _signals_for(facts)
    score = max(0, min(100, sum(signal.weight for signal in signals)))
    return MatchAssessment(
        score=score,
        signals=tuple(signals),
        automatic=_is_automatic(facts, score),
    )


def _signals_for(facts: MatchFacts) -> list[MatchSignal]:
    signals = []
    if facts.phone_match:
        signals.append(MatchSignal(code="exact_phone", weight=EXACT_PHONE_WEIGHT))
    if facts.domain_match:
        signals.append(MatchSignal(code="exact_domain", weight=EXACT_DOMAIN_WEIGHT))
    signals.extend(_name_signals(facts))
    signals.extend(_address_signals(facts))
    signals.extend(_distance_signals(facts.distance_m))
    if facts.category_relation == "same":
        signals.append(MatchSignal(code="same_category", weight=SAME_CATEGORY_WEIGHT))
    elif facts.category_relation == "incompatible":
        signals.append(
            MatchSignal(code="incompatible_category", weight=INCOMPATIBLE_CATEGORY_WEIGHT)
        )
    return signals


def _name_signals(facts: MatchFacts) -> list[MatchSignal]:
    if facts.exact_name:
        return [MatchSignal(code="exact_name", weight=EXACT_NAME_WEIGHT)]
    if facts.name_similarity >= NAME_SIMILARITY_90_THRESHOLD:
        return [
            MatchSignal(
                code="name_similarity_90",
                weight=NAME_SIMILARITY_90_WEIGHT,
                value=facts.name_similarity,
            )
        ]
    if facts.name_similarity >= NAME_SIMILARITY_78_THRESHOLD:
        return [
            MatchSignal(
                code="name_similarity_78",
                weight=NAME_SIMILARITY_78_WEIGHT,
                value=facts.name_similarity,
            )
        ]
    if facts.name_similarity >= NAME_SIMILARITY_65_THRESHOLD:
        return [
            MatchSignal(
                code="name_similarity_65",
                weight=NAME_SIMILARITY_65_WEIGHT,
                value=facts.name_similarity,
            )
        ]
    return []


def _address_signals(facts: MatchFacts) -> list[MatchSignal]:
    if facts.exact_address:
        return [MatchSignal(code="exact_address", weight=EXACT_ADDRESS_WEIGHT)]
    if facts.address_similarity >= ADDRESS_SIMILARITY_80_THRESHOLD:
        return [
            MatchSignal(
                code="address_similarity_80",
                weight=ADDRESS_SIMILARITY_80_WEIGHT,
                value=facts.address_similarity,
            )
        ]
    return []


def _distance_signals(distance_m: float | None) -> list[MatchSignal]:
    if distance_m is None:
        return []
    if distance_m <= DISTANCE_25M_THRESHOLD:
        return [MatchSignal(code="distance_25m", weight=DISTANCE_25M_WEIGHT, value=distance_m)]
    if distance_m <= DISTANCE_75M_THRESHOLD:
        return [MatchSignal(code="distance_75m", weight=DISTANCE_75M_WEIGHT, value=distance_m)]
    if distance_m <= DISTANCE_250M_THRESHOLD:
        return [MatchSignal(code="distance_250m", weight=DISTANCE_250M_WEIGHT, value=distance_m)]
    if distance_m <= DISTANCE_500M_THRESHOLD:
        return [MatchSignal(code="distance_500m", weight=DISTANCE_500M_WEIGHT, value=distance_m)]
    return []


def _is_automatic(facts: MatchFacts, score: int) -> bool:
    if facts.category_relation == "incompatible":
        return False
    if score < AUTOMATIC_SCORE_THRESHOLD or facts.distance_m is None:
        return False
    contact_gate = (
        (facts.phone_match or facts.domain_match)
        and facts.distance_m <= AUTOMATIC_CONTACT_MAX_DISTANCE_M
        and facts.name_similarity >= NAME_SIMILARITY_65_THRESHOLD
    )
    exact_details_gate = (
        facts.exact_name
        and facts.exact_address
        and facts.distance_m <= AUTOMATIC_EXACT_DETAILS_MAX_DISTANCE_M
    )
    return contact_gate or exact_details_gate
