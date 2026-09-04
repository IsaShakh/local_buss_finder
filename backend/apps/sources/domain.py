from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from common.json_types import JSONValue


@dataclass(frozen=True)
class SourceProvenance:
    dataset_version: str
    source_url: str | None
    attribution: str
    license_code: str


@dataclass(frozen=True)
class SourcePayload:
    external_id: str
    payload: dict[str, JSONValue]
    fetched_at: datetime
    provenance: SourceProvenance


@dataclass(frozen=True)
class RawBusinessRecord:
    external_id: str
    raw_name: str | None
    raw_category: str | None
    raw_address: str | None
    raw_phones: tuple[str, ...]
    raw_emails: tuple[str, ...]
    raw_websites: tuple[str, ...]
    raw_social_urls: dict[str, tuple[str, ...]]
    longitude: float | None
    latitude: float | None


class SourcePayloadParseError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class SourceRecordConflictError(Exception):
    pass


@dataclass(frozen=True)
class PersistedSourceRecord:
    source_record_id: UUID
    created: bool
    raw_payload_key: str
    checksum: str
    normalization_status: Literal["pending", "failed"]
