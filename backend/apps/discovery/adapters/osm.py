import hashlib
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime
from typing import Any, Protocol, cast

import httpx
from django.conf import settings
from django.utils import timezone

from apps.discovery.domain import (
    DiscoveryRequest,
    JSONValue,
    RawBusinessRecord,
    SourcePayload,
    SourceProvenance,
)
from apps.discovery.errors import (
    InvalidSourcePayload,
    PermanentSourceError,
    RateLimitedSourceError,
    TransientSourceError,
)
from apps.discovery.osm_query import build_overpass_query
from apps.sources.models import Source
from common.json_types import canonical_json_bytes

ATTRIBUTION = "© OpenStreetMap contributors"
LICENSE_CODE = "ODbL-1.0"
DEFAULT_MAX_SIZE_BYTES = 268_435_456
CATEGORY_KEYS = ("amenity", "office", "tourism", "shop")
SOCIAL_TAGS = {
    "facebook": "contact:facebook",
    "instagram": "contact:instagram",
    "twitter": "contact:twitter",
    "x": "contact:x",
}


class OverpassFetcher(Protocol):
    def fetch(self, query: str) -> dict[str, JSONValue]: ...


class OverpassClient:
    def __init__(self, *, url: str, timeout_seconds: int, user_agent: str) -> None:
        self.url = url
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent

    def fetch(self, query: str) -> dict[str, JSONValue]:
        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                headers={"User-Agent": self.user_agent, "Accept": "application/json"},
            ) as client:
                response = client.post(self.url, data={"data": query})
        except httpx.RequestError as error:
            raise TransientSourceError("SOURCE_TIMEOUT", str(error)) from error

        if response.status_code == 429:
            raise RateLimitedSourceError(_retry_after_seconds(response))
        if response.status_code >= 500:
            raise TransientSourceError(
                "SOURCE_UNAVAILABLE", f"Overpass returned HTTP {response.status_code}"
            )
        if response.status_code >= 400:
            raise PermanentSourceError(
                "INVALID_SOURCE_REQUEST", f"Overpass returned HTTP {response.status_code}"
            )

        try:
            payload = response.json()
        except ValueError as error:
            raise InvalidSourcePayload("Overpass response is not valid JSON") from error
        if not isinstance(payload, dict):
            raise InvalidSourcePayload("Overpass response must be a JSON object")
        return cast(dict[str, JSONValue], payload)


def _retry_after_seconds(response: httpx.Response) -> int | None:
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        seconds = int(value)
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


def _tags(payload: Mapping[str, JSONValue]) -> Mapping[str, JSONValue]:
    tags = payload.get("tags")
    return tags if isinstance(tags, Mapping) else {}


def _provider_category(payload: Mapping[str, JSONValue]) -> str | None:
    tags = _tags(payload)
    for key in CATEGORY_KEYS:
        value = tags.get(key)
        if isinstance(value, str) and value:
            return f"{key}={value}"
    return None


def _tag_values(tags: Mapping[str, JSONValue], *keys: str) -> tuple[str, ...]:
    values = []
    for key in keys:
        value = tags.get(key)
        if not isinstance(value, str):
            continue
        values.extend(item for part in value.split(";") if (item := part.strip()))
    return tuple(values)


def _address(tags: Mapping[str, JSONValue]) -> str | None:
    values = []
    for key in ("street", "housenumber", "suburb", "city", "postcode"):
        value = tags.get(f"addr:{key}")
        if isinstance(value, str) and value:
            values.append(value)
    return ", ".join(values) or None


def _social_urls(tags: Mapping[str, JSONValue]) -> dict[str, tuple[str, ...]]:
    return {
        provider: values
        for provider, tag in SOCIAL_TAGS.items()
        if (values := _tag_values(tags, tag))
    }


def _numeric(value: JSONValue | None) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _coordinates(payload: Mapping[str, JSONValue]) -> tuple[float | None, float | None]:
    if payload.get("type") == "node":
        return _numeric(payload.get("lon")), _numeric(payload.get("lat"))

    center = payload.get("center")
    if not isinstance(center, Mapping):
        return None, None
    return _numeric(center.get("lon")), _numeric(center.get("lat"))


def _external_id(payload: dict[str, JSONValue]) -> str:
    element_type = payload.get("type")
    element_id = payload.get("id")
    if (
        element_type in {"node", "way", "relation"}
        and isinstance(element_id, (str, int))
        and not isinstance(element_id, bool)
        and str(element_id).strip()
    ):
        return f"{element_type}/{element_id}"
    checksum = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return f"invalid:{checksum}"


def _normalize_endpoint(endpoint: str) -> str:
    return endpoint.strip().rstrip("/")


def _validated_operational_limits(timeout_seconds: Any, max_size_bytes: Any) -> tuple[int, int]:
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, int)
        or timeout_seconds <= 0
        or isinstance(max_size_bytes, bool)
        or not isinstance(max_size_bytes, int)
        or max_size_bytes <= 0
    ):
        raise PermanentSourceError(
            "SOURCE_CONFIGURATION", "OSM resource limits must be positive integers"
        )
    return timeout_seconds, max_size_bytes


class OpenStreetMapAdapter:
    source_code = "osm"

    def __init__(
        self,
        *,
        client: OverpassFetcher | None = None,
        endpoint_url: str | None = None,
        dataset_version: str | None = None,
        timeout_seconds: int | None = None,
        max_size_bytes: int | None = None,
        clock: Callable[[], datetime] = timezone.now,
    ) -> None:
        self._client = client
        self._configured_endpoint = endpoint_url
        self._configured_dataset_version = dataset_version
        self._configured_timeout_seconds = timeout_seconds
        self._configured_max_size_bytes = max_size_bytes
        self._clock = clock
        self._resolved_dataset_version: str | None = None

    @property
    def endpoint_url(self) -> str:
        configured = (
            settings.OVERPASS_URL
            if self._configured_endpoint is None
            else self._configured_endpoint
        )
        endpoint = _normalize_endpoint(configured)
        if not endpoint:
            raise PermanentSourceError("OVERPASS_NOT_CONFIGURED", "OVERPASS_URL is empty")
        return endpoint

    @property
    def client(self) -> OverpassFetcher:
        if self._client is None:
            timeout_seconds, _ = self._operational_limits()
            self._client = OverpassClient(
                url=self.endpoint_url,
                timeout_seconds=timeout_seconds,
                user_agent=settings.SOURCE_USER_AGENT,
            )
        return self._client

    def _operational_limits(self) -> tuple[int, int]:
        if (
            self._configured_timeout_seconds is not None
            and self._configured_max_size_bytes is not None
        ):
            return _validated_operational_limits(
                self._configured_timeout_seconds, self._configured_max_size_bytes
            )

        try:
            source = Source.objects.only("timeout_seconds", "settings").get(code=self.source_code)
        except Source.DoesNotExist as error:
            raise PermanentSourceError("SOURCE_CONFIGURATION", str(error)) from error

        timeout_seconds: Any = (
            self._configured_timeout_seconds
            if self._configured_timeout_seconds is not None
            else source.timeout_seconds
        )
        if self._configured_max_size_bytes is not None:
            max_size_bytes: Any = self._configured_max_size_bytes
        elif isinstance(source.settings, Mapping):
            max_size_bytes = source.settings.get("max_size_bytes", DEFAULT_MAX_SIZE_BYTES)
        else:
            raise PermanentSourceError(
                "SOURCE_CONFIGURATION", "OSM source settings must be a JSON object"
            )
        return _validated_operational_limits(timeout_seconds, max_size_bytes)

    def resolve_dataset_version(self) -> str:
        if self._resolved_dataset_version is not None:
            return self._resolved_dataset_version

        endpoint = self.endpoint_url
        configured = (
            settings.OSM_DATASET_VERSION
            if self._configured_dataset_version is None
            else self._configured_dataset_version
        ).strip()
        if configured:
            self._resolved_dataset_version = configured
            return configured

        settings_module = getattr(settings, "SETTINGS_MODULE", "")
        if not settings.DEBUG and not settings_module.endswith(".testing"):
            raise PermanentSourceError(
                "OSM_DATASET_VERSION_NOT_CONFIGURED",
                "OSM_DATASET_VERSION is required outside development and testing",
            )

        timestamp = self._clock().astimezone(UTC).isoformat().replace("+00:00", "Z")
        endpoint_digest = hashlib.sha256(endpoint.encode()).hexdigest()[:12]
        self._resolved_dataset_version = f"overpass-live:{endpoint_digest}:{timestamp}"
        return self._resolved_dataset_version

    def discover(self, request: DiscoveryRequest) -> Iterator[SourcePayload]:
        timeout_seconds, max_size_bytes = self._operational_limits()
        query = build_overpass_query(
            bbox=request.bbox,
            selectors=request.external_categories,
            timeout_seconds=timeout_seconds,
            max_size_bytes=max_size_bytes,
        )
        response = self.client.fetch(query)
        elements = response.get("elements")
        if not isinstance(elements, list):
            raise InvalidSourcePayload("Overpass response has no elements list")

        emitted = 0
        for item in elements:
            if not isinstance(item, dict):
                raise InvalidSourcePayload("Overpass element must be a JSON object")
            payload = cast(dict[str, JSONValue], item)
            if _provider_category(payload) not in request.external_categories:
                continue
            yield SourcePayload(
                external_id=_external_id(payload),
                payload=payload,
                fetched_at=timezone.now(),
                provenance=SourceProvenance(
                    dataset_version=request.dataset_version,
                    source_url=None,
                    attribution=ATTRIBUTION,
                    license_code=LICENSE_CODE,
                ),
            )
            emitted += 1
            if request.result_limit is not None and emitted >= request.result_limit:
                return

    def parse_payload(self, source_payload: SourcePayload) -> RawBusinessRecord:
        if source_payload.external_id.startswith("invalid:"):
            raise InvalidSourcePayload("OSM payload has no usable element type/id")

        payload = source_payload.payload
        tags = _tags(payload)
        longitude, latitude = _coordinates(payload)
        raw_name = tags.get("name")
        return RawBusinessRecord(
            external_id=source_payload.external_id,
            raw_name=raw_name if isinstance(raw_name, str) and raw_name else None,
            raw_category=_provider_category(payload),
            raw_address=_address(tags),
            raw_phones=_tag_values(tags, "contact:phone", "phone"),
            raw_emails=_tag_values(tags, "contact:email", "email"),
            raw_websites=_tag_values(tags, "contact:website", "website", "url"),
            raw_social_urls=_social_urls(tags),
            longitude=longitude,
            latitude=latitude,
        )
