import phonenumbers


class InvalidPhoneNumber(ValueError):
    pass


def normalize_phone(raw: str, *, default_region: str = "TR") -> str:
    try:
        parsed = phonenumbers.parse(raw, default_region)
    except phonenumbers.NumberParseException as error:
        raise InvalidPhoneNumber from error
    if not phonenumbers.is_valid_number(parsed):
        raise InvalidPhoneNumber
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
