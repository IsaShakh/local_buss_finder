from collections.abc import Iterable, Mapping
from urllib.parse import urlsplit, urlunsplit

from .urls import InvalidUrl, normalize_url


def normalize_social_urls(values: Mapping[str, Iterable[str]]) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for provider, raw_urls in values.items():
        normalized: list[str] = []
        for raw_url in raw_urls:
            try:
                url = normalize_url(raw_url)
            except InvalidUrl:
                continue
            parts = urlsplit(url)
            url = urlunsplit(("https", parts.netloc, parts.path, parts.query, ""))
            if url not in normalized:
                normalized.append(url)
        result[provider] = tuple(normalized)
    return result
