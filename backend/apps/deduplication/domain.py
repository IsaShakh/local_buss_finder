from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class MatchFacts:
    source_identity: bool
    phone_match: bool
    domain_match: bool
    exact_name: bool
    name_similarity: float
    exact_address: bool
    address_similarity: float
    distance_m: float | None
    category_relation: Literal["same", "neutral", "incompatible"]


@dataclass(frozen=True)
class MatchSignal:
    code: str
    weight: int
    value: str | float | None = None


@dataclass(frozen=True)
class MatchAssessment:
    score: int
    signals: tuple[MatchSignal, ...]
    automatic: bool
