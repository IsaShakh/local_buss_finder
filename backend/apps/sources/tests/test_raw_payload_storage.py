import gzip
import hashlib
import json
from uuid import UUID

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from apps.sources.storage import RawStorageUnavailable, S3RawPayloadStore
from common.json_types import canonical_json_bytes


def _client_error(*, code: str, status_code: int) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": code, "Message": code},
            "ResponseMetadata": {"HTTPStatusCode": status_code},
        },
        "PutObject",
    )


class FailingS3Client:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def put_object(self, **_kwargs) -> None:
        raise self.error

    def get_object(self, **_kwargs) -> None:
        raise self.error


def test_equivalent_json_produces_same_content_addressed_key(fake_s3_client):
    store = S3RawPayloadStore(client=fake_s3_client, bucket="raw-test")
    campaign_id = UUID("00000000-0000-0000-0000-000000000001")
    metadata = {"payload-schema-version": "1", "source-dataset-version": "2026-09"}

    first = store.put_json(
        source_code="osm",
        campaign_id=campaign_id,
        external_id="node/42",
        payload={"name": "Diş", "id": 42},
        metadata=metadata,
    )
    second = store.put_json(
        source_code="osm",
        campaign_id=campaign_id,
        external_id="node/42",
        payload={"id": 42, "name": "Diş"},
        metadata=metadata,
    )

    expected_sha256 = hashlib.sha256(b'{"id":42,"name":"Di\xc5\x9f"}').hexdigest()
    external_id_sha256 = hashlib.sha256(b"node/42").hexdigest()
    assert first == second
    assert first.sha256 == expected_sha256
    assert first.key == (f"raw/osm/{campaign_id}/{external_id_sha256}/{expected_sha256}.json.gz")


def test_unicode_round_trip_has_zero_gzip_mtime_and_exact_metadata(fake_s3_client):
    store = S3RawPayloadStore(client=fake_s3_client, bucket="raw-test")
    campaign_id = UUID("00000000-0000-0000-0000-000000000001")
    payload = {"id": 42, "name": "Çağlar Diş Kliniği"}

    stored = store.put_json(
        source_code="osm",
        campaign_id=campaign_id,
        external_id="node/42",
        payload=payload,
        metadata={"payload-schema-version": "1", "source-dataset-version": "2026-09"},
    )

    response = fake_s3_client.get_object(Bucket="raw-test", Key=stored.key)
    compressed = response["Body"].read()
    assert compressed[4:8] == b"\x00\x00\x00\x00"
    assert json.loads(gzip.decompress(compressed)) == payload
    head = fake_s3_client.head_object(Bucket="raw-test", Key=stored.key)
    assert head["ContentLength"] == stored.size_bytes == len(compressed)
    assert head["ContentType"] == "application/json"
    assert head["ContentEncoding"] == "gzip"
    assert head["Metadata"] == {
        "source-code": "osm",
        "campaign-id": str(campaign_id),
        "external-id": "node/42",
        "sha256": stored.sha256,
        "payload-schema-version": "1",
        "source-dataset-version": "2026-09",
    }
    assert store.get_json(stored.key) == payload


def test_equal_payload_for_different_external_ids_has_distinct_metadata(fake_s3_client):
    store = S3RawPayloadStore(client=fake_s3_client, bucket="raw-test")
    campaign_id = UUID("00000000-0000-0000-0000-000000000001")
    payload = {"name": "Payload without embedded provider ID"}
    metadata = {"payload-schema-version": "1", "source-dataset-version": "fixture"}

    first = store.put_json(
        source_code="osm",
        campaign_id=campaign_id,
        external_id="node/1",
        payload=payload,
        metadata=metadata,
    )
    second = store.put_json(
        source_code="osm",
        campaign_id=campaign_id,
        external_id="node/2",
        payload=payload,
        metadata=metadata,
    )

    assert first.sha256 == second.sha256
    assert first.key != second.key
    first_meta = fake_s3_client.head_object(Bucket="raw-test", Key=first.key)["Metadata"]
    second_meta = fake_s3_client.head_object(Bucket="raw-test", Key=second.key)["Metadata"]
    assert first_meta["external-id"] == "node/1"
    assert second_meta["external-id"] == "node/2"


def test_canonical_json_rejects_non_json_nan():
    with pytest.raises(ValueError):
        canonical_json_bytes({"score": float("nan")})


@pytest.mark.parametrize(
    "error",
    [
        EndpointConnectionError(endpoint_url="https://s3.example.test"),
        _client_error(code="SlowDown", status_code=429),
        _client_error(code="InternalError", status_code=503),
    ],
)
def test_retryable_put_failures_become_provider_neutral(error):
    store = S3RawPayloadStore(client=FailingS3Client(error), bucket="raw-test")

    with pytest.raises(RawStorageUnavailable) as caught:
        store.put_json(
            source_code="osm",
            campaign_id=UUID("00000000-0000-0000-0000-000000000001"),
            external_id="node/42",
            payload={"id": 42},
            metadata={"payload-schema-version": "1", "source-dataset-version": "fixture"},
        )

    assert caught.value.code == "RAW_STORAGE_UNAVAILABLE"
    assert caught.value.__cause__ is error


def test_retryable_get_failure_becomes_provider_neutral():
    error = EndpointConnectionError(endpoint_url="https://s3.example.test")
    store = S3RawPayloadStore(client=FailingS3Client(error), bucket="raw-test")

    with pytest.raises(RawStorageUnavailable) as caught:
        store.get_json("raw/osm/object.json.gz")

    assert caught.value.__cause__ is error


@pytest.mark.parametrize(
    "error",
    [
        _client_error(code="AccessDenied", status_code=403),
        _client_error(code="UnexpectedStatus", status_code=600),
    ],
)
def test_non_retryable_s3_failure_is_not_masked(error):
    store = S3RawPayloadStore(client=FailingS3Client(error), bucket="raw-test")

    with pytest.raises(ClientError) as caught:
        store.put_json(
            source_code="osm",
            campaign_id=UUID("00000000-0000-0000-0000-000000000001"),
            external_id="node/42",
            payload={"id": 42},
            metadata={"payload-schema-version": "1", "source-dataset-version": "fixture"},
        )

    assert caught.value is error
