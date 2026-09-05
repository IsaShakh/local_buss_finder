import gzip
import hashlib
import json
from collections.abc import Mapping
from time import perf_counter
from typing import Any, cast
from uuid import UUID

from botocore.exceptions import (
    ClientError,
    HTTPClientError,
)
from botocore.exceptions import (
    ConnectionError as BotoCoreConnectionError,
)

from common.json_types import JSONValue, canonical_json_bytes
from common.observability import structured_event

from .base import RawStorageUnavailable, StoredPayload

CONTENT_TYPE = "application/json"
CONTENT_ENCODING = "gzip"
RETRYABLE_ERROR_CODES = frozenset(
    {
        "InternalError",
        "RequestTimeout",
        "RequestTimeoutException",
        "ServiceUnavailable",
        "SlowDown",
        "Throttling",
        "ThrottlingException",
        "TooManyRequestsException",
    }
)


def _is_retryable_client_error(error: ClientError) -> bool:
    error_code = error.response.get("Error", {}).get("Code")
    status_code = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return error_code in RETRYABLE_ERROR_CODES or (
        isinstance(status_code, int) and (status_code in {408, 429} or 500 <= status_code < 600)
    )


class S3RawPayloadStore:
    def __init__(self, *, client: Any, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

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
        payload_sha256 = hashlib.sha256(raw).hexdigest()
        external_id_sha256 = hashlib.sha256(external_id.encode("utf-8")).hexdigest()
        key = f"raw/{source_code}/{campaign_id}/{external_id_sha256}/{payload_sha256}.json.gz"
        body = gzip.compress(raw, mtime=0)
        object_metadata = {
            "source-code": source_code,
            "campaign-id": str(campaign_id),
            "external-id": external_id,
            "sha256": payload_sha256,
            "payload-schema-version": metadata["payload-schema-version"],
            "source-dataset-version": metadata["source-dataset-version"],
        }

        started_at = perf_counter()
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body,
                ContentType=CONTENT_TYPE,
                ContentEncoding=CONTENT_ENCODING,
                Metadata=object_metadata,
            )
        except (BotoCoreConnectionError, HTTPClientError) as error:
            raise RawStorageUnavailable from error
        except ClientError as error:
            if _is_retryable_client_error(error):
                raise RawStorageUnavailable from error
            raise

        structured_event(
            "storage.object.stored",
            campaign_id=campaign_id,
            correlation_id=str(campaign_id),
            source=source_code,
            duration_ms=round((perf_counter() - started_at) * 1000, 3),
            message="Raw payload object stored",
        )

        return StoredPayload(
            key=key,
            sha256=payload_sha256,
            size_bytes=len(body),
            content_type=CONTENT_TYPE,
            content_encoding=CONTENT_ENCODING,
        )

    def get_json(self, key: str) -> dict[str, JSONValue]:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            body = response["Body"].read()
        except (BotoCoreConnectionError, HTTPClientError) as error:
            raise RawStorageUnavailable from error
        except ClientError as error:
            if _is_retryable_client_error(error):
                raise RawStorageUnavailable from error
            raise

        payload = json.loads(gzip.decompress(body))
        return cast(dict[str, JSONValue], payload)
