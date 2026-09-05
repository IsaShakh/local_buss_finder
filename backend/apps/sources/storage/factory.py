from typing import Any

import boto3
from botocore.config import Config
from django.conf import settings

from .s3 import S3RawPayloadStore


def build_raw_payload_store(*, client: Any | None = None) -> S3RawPayloadStore:
    if client is None:
        addressing_style = "path" if settings.S3_FORCE_PATH_STYLE else "auto"
        client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY_ID,
            aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
            region_name=settings.S3_REGION_NAME,
            config=Config(s3={"addressing_style": addressing_style}),
        )
    return S3RawPayloadStore(client=client, bucket=settings.S3_BUCKET_NAME)
