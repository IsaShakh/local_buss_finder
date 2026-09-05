import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")


def normalize_address(raw_address: str | None) -> str:
    if raw_address is None:
        return ""
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", raw_address)).strip()
