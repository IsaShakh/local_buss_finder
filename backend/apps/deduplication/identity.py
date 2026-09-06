from collections.abc import Iterable
from urllib.parse import urlsplit

EXCLUDED_OFFICIAL_DOMAIN_HOSTS = frozenset(
    {
        "booking.com",
        "facebook.com",
        "foursquare.com",
        "google.com",
        "instagram.com",
        "linkedin.com",
        "tiktok.com",
        "tripadvisor.com",
        "twitter.com",
        "x.com",
        "yelp.com",
        "youtube.com",
    }
)


def extract_official_domains(websites: Iterable[str]) -> tuple[str, ...]:
    """Return sorted, distinct hostnames that can identify a business website."""
    domains = set()
    for website in websites:
        try:
            parts = urlsplit(website.strip())
            port = parts.port
        except (AttributeError, ValueError):
            continue
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            continue
        if port is not None and not 0 <= port <= 65535:
            continue
        host = parts.hostname.lower()
        host = host.removeprefix("www.")
        if _is_excluded_host(host):
            continue
        domains.add(host)
    return tuple(sorted(domains))


def _is_excluded_host(host: str) -> bool:
    return any(
        host == excluded_host or host.endswith(f".{excluded_host}")
        for excluded_host in EXCLUDED_OFFICIAL_DOMAIN_HOSTS
    )
