import re
import unicodedata
from collections.abc import Iterable

from apps.normalization.domain import NormalizedStrings

_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def normalize_emails(values: Iterable[str]) -> NormalizedStrings:
    normalized: list[str] = []
    warnings: list[str] = []
    for raw in values:
        value = unicodedata.normalize("NFKC", raw).strip().casefold()
        if not _EMAIL.fullmatch(value):
            if "INVALID_EMAIL" not in warnings:
                warnings.append("INVALID_EMAIL")
            continue
        if value not in normalized:
            normalized.append(value)
    return NormalizedStrings(tuple(normalized), tuple(warnings))
