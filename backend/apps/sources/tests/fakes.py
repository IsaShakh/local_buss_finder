import gzip
import hashlib
import json
import threading
from collections.abc import Mapping
from uuid import UUID

from apps.sources.storage import StoredPayload
from common.json_types import JSONValue, canonical_json_bytes


class InMemoryRawPayloadStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._objects: dict[str, bytes] = {}

    @property
    def object_count(self) -> int:
        with self._lock:
            return len(self._objects)

    def put_json(
        self,
        *,
        source_code: str,
        campaign_id: UUID,
        external_id: str,
        payload: dict[str, JSONValue],
        metadata: Mapping[str, str],
    ) -> StoredPayload:
        raw = canonical_json_bytes(payload)
        checksum = hashlib.sha256(raw).hexdigest()
        body = gzip.compress(raw, mtime=0)
        external_id_checksum = hashlib.sha256(external_id.encode("utf-8")).hexdigest()
        key = f"raw/{source_code}/{campaign_id}/{external_id_checksum}/{checksum}.json.gz"
        with self._lock:
            self._objects.setdefault(key, body)
        return StoredPayload(
            key=key,
            sha256=checksum,
            size_bytes=len(body),
            content_type="application/json",
            content_encoding="gzip",
        )

    def get_json(self, key: str) -> dict[str, JSONValue]:
        with self._lock:
            body = self._objects[key]
        return json.loads(gzip.decompress(body))
