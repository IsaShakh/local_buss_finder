from apps.normalization.domain import NormalizedStrings
from apps.normalization.rules.emails import normalize_emails


def test_emails_are_lowercased_deduplicated_and_invalid_values_warn():
    assert normalize_emails([" Test@Example.COM ", "bad", "test@example.com"]) == (
        NormalizedStrings(("test@example.com",), ("INVALID_EMAIL",))
    )
