import re
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured

CONTACT_URL_PATTERN = re.compile(r"https?://[^\s)]+", re.IGNORECASE)
CONTACT_EMAIL_PATTERN = re.compile(
    r"(?<![\w.+-])[A-Z0-9._%+-]+@([A-Z0-9.-]+\.[A-Z]{2,})(?![\w.-])",
    re.IGNORECASE,
)
PRODUCT_TOKEN_PATTERN = re.compile(
    r"^[A-Z0-9][A-Z0-9._-]*/[A-Z0-9][A-Z0-9._-]*(?:\s|$)",
    re.IGNORECASE,
)
PLACEHOLDER_HOST_SUFFIXES = ("localhost", "invalid", "example")


def _is_placeholder_hostname(hostname: str | None) -> bool:
    if not hostname:
        return True
    normalized = hostname.rstrip(".").casefold()
    return any(
        normalized == suffix or normalized.endswith(f".{suffix}")
        for suffix in PLACEHOLDER_HOST_SUFFIXES
    )


def _valid_contact(source_user_agent: str) -> bool:
    for match in CONTACT_URL_PATTERN.finditer(source_user_agent):
        parsed = urlparse(match.group())
        if parsed.scheme in {"http", "https"} and not _is_placeholder_hostname(parsed.hostname):
            return True

    for match in CONTACT_EMAIL_PATTERN.finditer(source_user_agent):
        if not _is_placeholder_hostname(match.group(1)):
            return True
    return False


def validate_live_osm_configuration(
    *,
    overpass_url: str,
    dataset_version: str,
    source_user_agent: str,
) -> None:
    endpoint = overpass_url.strip()
    if not endpoint:
        raise ImproperlyConfigured("OVERPASS_URL must be configured in production")

    parsed_endpoint = urlparse(endpoint)
    if (
        parsed_endpoint.scheme != "https"
        or parsed_endpoint.username is not None
        or parsed_endpoint.password is not None
        or _is_placeholder_hostname(parsed_endpoint.hostname)
    ):
        raise ImproperlyConfigured("OVERPASS_URL must be an HTTPS self-hosted or paid endpoint")

    if not dataset_version.strip():
        raise ImproperlyConfigured("OSM_DATASET_VERSION must identify the production snapshot")

    identity = source_user_agent.strip()
    if PRODUCT_TOKEN_PATTERN.match(identity) is None or not _valid_contact(identity):
        raise ImproperlyConfigured(
            "SOURCE_USER_AGENT must include a product/version token and real contact URI or email"
        )
