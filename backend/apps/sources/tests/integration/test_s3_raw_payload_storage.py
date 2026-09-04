from uuid import UUID

import pytest

pytestmark = pytest.mark.integration


def test_real_s3_round_trip_and_metadata(minio_store):
    campaign_id = UUID("00000000-0000-0000-0000-000000000001")
    payload = {"id": 42, "name": "Çağlar Diş Kliniği", "tags": ["diş", "sağlık"]}

    stored = minio_store.put_json(
        source_code="osm",
        campaign_id=campaign_id,
        external_id="node/42",
        payload=payload,
        metadata={"payload-schema-version": "1", "source-dataset-version": "garage-fixture"},
    )

    assert minio_store.get_json(stored.key) == payload
    head = minio_store.client.head_object(Bucket=minio_store.bucket, Key=stored.key)
    assert head["ContentLength"] == stored.size_bytes
    assert head["ContentType"] == "application/json"
    assert head["ContentEncoding"] == "gzip"
    assert head["Metadata"] == {
        "source-code": "osm",
        "campaign-id": str(campaign_id),
        "external-id": "node/42",
        "sha256": stored.sha256,
        "payload-schema-version": "1",
        "source-dataset-version": "garage-fixture",
    }
