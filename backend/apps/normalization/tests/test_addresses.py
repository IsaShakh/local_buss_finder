from apps.normalization.rules.addresses import normalize_address


def test_address_collapses_unicode_whitespace():
    assert normalize_address("  Atatürk  Cd.\n 12 ") == "Atatürk Cd. 12"


def test_missing_address_becomes_empty_string():
    assert normalize_address(None) == ""
