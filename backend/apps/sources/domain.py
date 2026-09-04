from dataclasses import dataclass
from typing import Literal
from uuid import UUID


class SourceRecordConflictError(Exception):
    pass


@dataclass(frozen=True)
class PersistedSourceRecord:
    source_record_id: UUID
    created: bool
    raw_payload_key: str
    checksum: str
    normalization_status: Literal["pending", "failed"]
