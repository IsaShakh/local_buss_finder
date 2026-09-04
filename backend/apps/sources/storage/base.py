from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from common.json_types import JSONValue


@dataclass(frozen=True)
class StoredPayload:
    key: str
    sha256: str
    size_bytes: int
    content_type: str
    content_encoding: str


class RawPayloadStore(Protocol):
    def put_json(
        self,
        *,
        source_code: str,
        campaign_id: UUID,
        external_id: str,
        payload: dict[str, JSONValue],
        metadata: Mapping[str, str],
    ) -> StoredPayload: ...

    def get_json(self, key: str) -> dict[str, JSONValue]: ...


class RawStorageUnavailable(Exception):
    code = "RAW_STORAGE_UNAVAILABLE"
