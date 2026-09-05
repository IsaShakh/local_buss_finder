import hashlib
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any, NoReturn, Protocol, cast
from urllib.parse import urlparse

from django.utils import timezone

from apps.discovery.domain import (
    DiscoveryRequest,
    JSONScalar,
    JSONValue,
    RawBusinessRecord,
    SourcePayload,
    SourceProvenance,
)
from apps.discovery.errors import (
    DiscoveryError,
    InvalidSourcePayload,
    PermanentSourceError,
    TransientSourceError,
)
from apps.sources.models import Source
from common.json_types import canonical_json_bytes

ATTRIBUTION = "Overture Maps Foundation"
LICENSE_CODE = "CDLA-Permissive-2.0/Apache-2.0"
BINARY_HEX_KEY = "$binary_hex"


class OvertureClient(Protocol):
    def latest_release(self) -> str: ...

    def iter_places(
        self,
        *,
        bbox: tuple[float, float, float, float],
        release: str,
    ) -> Iterator[dict[str, JSONValue]]: ...


class RecordBatch(Protocol):
    def to_pylist(self) -> list[dict[str, Any]]: ...


type LatestReleaseFn = Callable[[], str]
type RecordBatchReaderFn = Callable[..., Iterable[RecordBatch] | None]


def make_json_compatible(value: Any) -> JSONValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return cast(JSONScalar, value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {BINARY_HEX_KEY: bytes(value).hex()}
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): make_json_compatible(item) for key, item in value.items()}
    if isinstance(value, Sequence):
        return [make_json_compatible(item) for item in value]
    if hasattr(value, "as_py"):
        return make_json_compatible(value.as_py())
    if hasattr(value, "item"):
        return make_json_compatible(value.item())
    raise TypeError(f"unsupported provider value: {type(value).__name__}")


class OfficialOvertureClient:
    def __init__(
        self,
        *,
        timeout_seconds: int,
        latest_release_fn: LatestReleaseFn | None = None,
        record_batch_reader_fn: RecordBatchReaderFn | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self._latest_release_fn = latest_release_fn
        self._record_batch_reader_fn = record_batch_reader_fn

    def latest_release(self) -> str:
        if self._latest_release_fn is None:
            from overturemaps.core import get_latest_release

            self._latest_release_fn = get_latest_release
        return self._latest_release_fn()

    def iter_places(
        self,
        *,
        bbox: tuple[float, float, float, float],
        release: str,
    ) -> Iterator[dict[str, JSONValue]]:
        if self._record_batch_reader_fn is None:
            from overturemaps.core import record_batch_reader

            self._record_batch_reader_fn = record_batch_reader
        reader = self._record_batch_reader_fn(
            "place",
            bbox=bbox,
            release=release,
            connect_timeout=self.timeout_seconds,
            request_timeout=self.timeout_seconds,
            stac=True,
        )
        if reader is None:
            return
        for batch in reader:
            for row in batch.to_pylist():
                converted = make_json_compatible(row)
                if not isinstance(converted, dict):
                    raise TypeError("Overture place row must be a JSON object")
                yield converted


def _provider_category(payload: Mapping[str, JSONValue]) -> str | None:
    taxonomy = payload.get("taxonomy")
    if isinstance(taxonomy, Mapping):
        primary = taxonomy.get("primary")
        if isinstance(primary, str) and primary:
            return primary

    basic_category = payload.get("basic_category")
    if isinstance(basic_category, str) and basic_category:
        return basic_category

    categories = payload.get("categories")
    if isinstance(categories, Mapping):
        primary = categories.get("primary")
        if isinstance(primary, str) and primary:
            return primary
    return None


def _primary_name(payload: Mapping[str, JSONValue]) -> str | None:
    names = payload.get("names")
    if not isinstance(names, Mapping):
        return None
    primary = names.get("primary")
    return primary if isinstance(primary, str) and primary else None


def _string_tuple(value: JSONValue | None) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)


def _first_address(payload: Mapping[str, JSONValue]) -> str | None:
    addresses = payload.get("addresses")
    if not isinstance(addresses, list) or not addresses:
        return None
    first = addresses[0]
    if not isinstance(first, Mapping):
        return None
    freeform = first.get("freeform")
    if isinstance(freeform, str) and freeform:
        return freeform
    parts = [
        first.get(field)
        for field in ("house_number", "street", "locality", "region", "postcode", "country")
    ]
    readable = ", ".join(part for part in parts if isinstance(part, str) and part)
    return readable or None


def _social_provider(url: str) -> str:
    hostname = (urlparse(url).hostname or "").lower().removeprefix("www.")
    labels = hostname.split(".")
    return labels[-2] if len(labels) >= 2 else hostname or "other"


def _social_urls(payload: Mapping[str, JSONValue]) -> dict[str, tuple[str, ...]]:
    socials = payload.get("socials")
    grouped: dict[str, list[str]] = {}
    if isinstance(socials, Mapping):
        for provider, urls in socials.items():
            if not isinstance(provider, str):
                continue
            for url in _string_tuple(urls):
                grouped.setdefault(provider, []).append(url)
    elif isinstance(socials, list):
        for url in _string_tuple(socials):
            grouped.setdefault(_social_provider(url), []).append(url)
    return {provider: tuple(urls) for provider, urls in grouped.items()}


def _point_coordinates(payload: Mapping[str, JSONValue]) -> tuple[float | None, float | None]:
    geometry = payload.get("geometry")
    if not isinstance(geometry, Mapping):
        return None, None

    coordinates = geometry.get("coordinates")
    if isinstance(coordinates, list) and len(coordinates) >= 2:
        longitude, latitude = coordinates[:2]
        if (
            isinstance(longitude, (int, float))
            and not isinstance(longitude, bool)
            and isinstance(latitude, (int, float))
            and not isinstance(latitude, bool)
        ):
            return float(longitude), float(latitude)

    binary_hex = geometry.get(BINARY_HEX_KEY)
    if not isinstance(binary_hex, str):
        return None, None
    try:
        from shapely import from_wkb
        from shapely.errors import GEOSException

        point = from_wkb(bytes.fromhex(binary_hex))
        if point.geom_type != "Point":
            return None, None
        return float(point.x), float(point.y)
    except (GEOSException, TypeError, ValueError):
        return None, None


def _external_id(payload: dict[str, JSONValue]) -> str:
    provider_id = payload.get("id")
    if isinstance(provider_id, str) and provider_id.strip():
        return provider_id
    checksum = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return f"invalid:{checksum}"


def _is_network_error(error: BaseException) -> bool:
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, (TimeoutError, OSError)):
            return True
        current = current.__cause__ or current.__context__
    return False


def _raise_discovery_error(error: Exception) -> NoReturn:
    if isinstance(error, DiscoveryError):
        raise error
    if _is_network_error(error):
        raise TransientSourceError("SOURCE_TIMEOUT", str(error)) from error
    raise PermanentSourceError("INVALID_SOURCE_PAYLOAD", str(error)) from error


class OvertureAdapter:
    source_code = "overture"

    def __init__(self, *, client: OvertureClient | None = None) -> None:
        self._client = client

    @property
    def client(self) -> OvertureClient:
        if self._client is None:
            try:
                source = Source.objects.only("timeout_seconds").get(code=self.source_code)
            except Source.DoesNotExist as error:
                raise PermanentSourceError("SOURCE_CONFIGURATION", str(error)) from error
            self._client = OfficialOvertureClient(timeout_seconds=source.timeout_seconds)
        return self._client

    def resolve_dataset_version(self) -> str:
        try:
            release = self.client.latest_release()
        # overturemaps wraps STAC failures in a plain Exception.
        except Exception as error:  # noqa: BLE001
            _raise_discovery_error(error)
        if not isinstance(release, str) or not release.strip():
            raise PermanentSourceError("INVALID_SOURCE_PAYLOAD", "empty Overture release")
        return release

    def discover(self, request: DiscoveryRequest) -> Iterator[SourcePayload]:
        bbox = (request.bbox.west, request.bbox.south, request.bbox.east, request.bbox.north)
        emitted = 0
        try:
            for payload in self.client.iter_places(
                bbox=bbox,
                release=request.dataset_version,
            ):
                if _provider_category(payload) not in request.external_categories:
                    continue
                external_id = _external_id(payload)
                yield SourcePayload(
                    external_id=external_id,
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
        # Provider/PyArrow failures must leave this boundary as typed discovery errors.
        except Exception as error:  # noqa: BLE001
            _raise_discovery_error(error)

    def parse_payload(self, source_payload: SourcePayload) -> RawBusinessRecord:
        if source_payload.external_id.startswith("invalid:"):
            raise InvalidSourcePayload("Overture payload has no usable id")
        payload = source_payload.payload
        longitude, latitude = _point_coordinates(payload)
        return RawBusinessRecord(
            external_id=source_payload.external_id,
            raw_name=_primary_name(payload),
            raw_category=_provider_category(payload),
            raw_address=_first_address(payload),
            raw_phones=_string_tuple(payload.get("phones")),
            raw_emails=_string_tuple(payload.get("emails")),
            raw_websites=_string_tuple(payload.get("websites")),
            raw_social_urls=_social_urls(payload),
            longitude=longitude,
            latitude=latitude,
        )
