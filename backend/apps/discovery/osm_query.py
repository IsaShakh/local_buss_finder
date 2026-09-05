import re
from collections.abc import Sequence

from apps.discovery.domain import BoundingBox

SELECTOR_PATTERN = re.compile(r"^[a-z0-9_:.-]+=[a-z0-9_:.-]+$")


class InvalidSelector(ValueError):
    pass


def build_overpass_query(
    *,
    bbox: BoundingBox,
    selectors: Sequence[str],
    timeout_seconds: int,
    max_size_bytes: int,
) -> str:
    if not selectors:
        raise ValueError("selectors must not be empty")
    if isinstance(timeout_seconds, bool) or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if isinstance(max_size_bytes, bool) or max_size_bytes <= 0:
        raise ValueError("max_size_bytes must be positive")

    bbox_expression = f"{bbox.south},{bbox.west},{bbox.north},{bbox.east}"
    clauses = []
    for selector in selectors:
        if SELECTOR_PATTERN.fullmatch(selector) is None:
            raise InvalidSelector(selector)
        key, value = selector.split("=", maxsplit=1)
        clauses.append(f'nwr["{key}"="{value}"]({bbox_expression});')

    return (
        f"[out:json][timeout:{timeout_seconds}][maxsize:{max_size_bytes}];"
        f"({''.join(clauses)});out center tags;"
    )
