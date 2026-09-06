import pytest

from apps.deduplication.domain import MatchFacts
from apps.deduplication.scoring import assess_match


def facts(**overrides):
    values = {
        "source_identity": False,
        "phone_match": False,
        "domain_match": False,
        "exact_name": False,
        "name_similarity": 0.0,
        "exact_address": False,
        "address_similarity": 0.0,
        "distance_m": None,
        "category_relation": "neutral",
    }
    values.update(overrides)
    return MatchFacts(**values)


def signal_codes(assessment):
    return [signal.code for signal in assessment.signals]


def test_exact_source_identity_is_a_complete_automatic_match():
    """Catches losing the special exact-provider identity resolution path."""
    assessment = assess_match(facts(source_identity=True, category_relation="incompatible"))

    assert assessment.score == 100
    assert signal_codes(assessment) == ["source_identity"]
    assert assessment.automatic is True


@pytest.mark.parametrize(
    ("similarity", "score", "signal_code"),
    [
        (0.90, 25, "name_similarity_90"),
        (0.899, 18, "name_similarity_78"),
        (0.78, 18, "name_similarity_78"),
        (0.779, 10, "name_similarity_65"),
        (0.65, 10, "name_similarity_65"),
        (0.649, 0, None),
    ],
)
def test_name_similarity_uses_one_expected_boundary_tier(similarity, score, signal_code):
    """Catches shifted name-similarity cutoffs or cumulative name tier weights."""
    assessment = assess_match(facts(name_similarity=similarity))

    assert assessment.score == score
    assert signal_codes(assessment) == ([] if signal_code is None else [signal_code])


def test_exact_name_replaces_similarity_tiers():
    """Catches stacking exact-name and similarity points for one evidence field."""
    assessment = assess_match(facts(exact_name=True, name_similarity=1.0))

    assert assessment.score == 30
    assert signal_codes(assessment) == ["exact_name"]


@pytest.mark.parametrize(
    ("exact_address", "similarity", "score", "signal_code"),
    [
        (True, 1.0, 20, "exact_address"),
        (False, 0.80, 12, "address_similarity_80"),
        (False, 0.799, 0, None),
    ],
)
def test_address_uses_one_expected_boundary_tier(exact_address, similarity, score, signal_code):
    """Catches shifted address cutoffs or stacking exact and fuzzy address points."""
    assessment = assess_match(facts(exact_address=exact_address, address_similarity=similarity))

    assert assessment.score == score
    assert signal_codes(assessment) == ([] if signal_code is None else [signal_code])


@pytest.mark.parametrize(
    ("distance_m", "score", "signal_code"),
    [
        (25.0, 25, "distance_25m"),
        (25.001, 20, "distance_75m"),
        (75.0, 20, "distance_75m"),
        (75.001, 12, "distance_250m"),
        (250.0, 12, "distance_250m"),
        (250.001, 5, "distance_500m"),
        (500.0, 5, "distance_500m"),
        (500.001, 0, None),
        (None, 0, None),
    ],
)
def test_distance_uses_one_expected_boundary_tier(distance_m, score, signal_code):
    """Catches shifted distance cutoffs or cumulative distance points."""
    assessment = assess_match(facts(distance_m=distance_m))

    assert assessment.score == score
    assert signal_codes(assessment) == ([] if signal_code is None else [signal_code])


@pytest.mark.parametrize(
    ("relation", "score", "signal_code"),
    [
        ("same", 10, "same_category"),
        ("neutral", 0, None),
        ("incompatible", 0, "incompatible_category"),
    ],
)
def test_category_relation_adds_or_removes_expected_evidence(relation, score, signal_code):
    """Catches compatibility bonuses, penalties, or neutral handling changing behavior."""
    assessment = assess_match(facts(category_relation=relation))

    assert assessment.score == score
    assert signal_codes(assessment) == ([] if signal_code is None else [signal_code])


def test_score_is_clamped_and_signals_have_a_stable_order():
    """Catches overflow scores or an unstable API-facing explanation order."""
    assessment = assess_match(
        facts(
            phone_match=True,
            domain_match=True,
            exact_name=True,
            exact_address=True,
            distance_m=25,
            category_relation="same",
        )
    )

    assert assessment.score == 100
    assert signal_codes(assessment) == [
        "exact_phone",
        "exact_domain",
        "exact_name",
        "exact_address",
        "distance_25m",
        "same_category",
    ]


def test_score_is_clamped_at_zero_for_incompatible_categories():
    """Catches negative scores leaking into persisted candidate scores."""
    assessment = assess_match(facts(category_relation="incompatible"))

    assert assessment.score == 0


def test_exact_phone_gate_is_automatic_at_its_boundary():
    """Catches rejecting approved close phone/domain evidence at the 250m boundary."""
    assessment = assess_match(
        facts(
            phone_match=True,
            exact_name=True,
            name_similarity=0.65,
            exact_address=True,
            distance_m=250,
        )
    )

    assert assessment.score == 97
    assert assessment.automatic is True


def test_exact_name_and_address_gate_is_automatic_at_its_boundary():
    """Catches rejecting approved exact name/address evidence at the 75m boundary."""
    assessment = assess_match(
        facts(exact_name=True, exact_address=True, distance_m=75, category_relation="same")
    )

    assert assessment.score == 80
    assert assessment.automatic is True


def test_distant_shared_phone_and_domain_is_reviewable_but_not_automatic():
    """Catches automatic branch attachment based only on shared contact identifiers."""
    assessment = assess_match(facts(phone_match=True, domain_match=True, distance_m=500.001))

    assert assessment.score == 70
    assert assessment.score >= 55
    assert assessment.automatic is False


def test_incompatible_categories_block_non_source_automatic_attachment():
    """Catches category-incompatible businesses being attached without exact source identity."""
    assessment = assess_match(
        facts(
            phone_match=True,
            exact_name=True,
            exact_address=True,
            distance_m=75,
            category_relation="incompatible",
        )
    )

    assert assessment.score == 80
    assert assessment.automatic is False
