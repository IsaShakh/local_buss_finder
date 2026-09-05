import pytest

from apps.normalization.rules.phones import InvalidPhoneNumber, normalize_phone


def test_turkish_mobile_phone_is_e164():
    assert normalize_phone("0532 123 45 67", default_region="TR") == "+905321234567"


def test_invalid_phone_is_rejected_by_pure_rule():
    with pytest.raises(InvalidPhoneNumber):
        normalize_phone("not-a-phone", default_region="TR")
