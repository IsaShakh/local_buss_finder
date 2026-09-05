import re
import unicodedata
from dataclasses import dataclass

_WHITESPACE = re.compile(r"\s+")
_TERMINAL_LEGAL_SUFFIX = re.compile(
    r"(?:\s+)(?:ltd\.?\s+şti\.?|ltd\.?|a\.\s*ş\.?|anonim\s+şirketi)\s*$",
    flags=re.IGNORECASE,
)
_NON_WORD = re.compile(r"[^0-9a-z]+")
_TURKISH_TRANSLATION = str.maketrans(
    {
        "ç": "c",
        "ğ": "g",
        "ı": "i",
        "ö": "o",
        "ş": "s",
        "ü": "u",
    }
)


class MissingName(ValueError):
    pass


@dataclass(frozen=True)
class NameParts:
    display_name: str
    normalized_name: str
    match_name: str


def _normalize_whitespace(value: str) -> str:
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", value)).strip()


def _casefold_turkish(value: str) -> str:
    return value.casefold().replace("\N{COMBINING DOT ABOVE}", "")


def normalize_name(raw: str) -> NameParts:
    display_name = _normalize_whitespace(raw)
    if not display_name:
        raise MissingName
    display_name = _TERMINAL_LEGAL_SUFFIX.sub("", display_name).strip()
    if not display_name:
        raise MissingName
    normalized_name = _casefold_turkish(display_name)
    transliterated = normalized_name.translate(_TURKISH_TRANSLATION)
    match_name = _WHITESPACE.sub(" ", _NON_WORD.sub(" ", transliterated)).strip()
    return NameParts(display_name, normalized_name, match_name)
