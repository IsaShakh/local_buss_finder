import boto3
from botocore.config import Config
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


def check_database() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        if cursor.fetchone() != (1,):
            raise RuntimeError("database readiness query returned an unexpected result")


def check_redis() -> None:
    key = "system:health:ready"
    value = "ok"
    cache.set(key, value, timeout=5)
    if cache.get(key) != value:
        raise RuntimeError("redis readiness value did not round-trip")


def check_object_storage() -> None:
    addressing_style = "path" if settings.S3_FORCE_PATH_STYLE else "auto"
    client = boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL,
        aws_access_key_id=settings.S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
        region_name=settings.S3_REGION_NAME,
        config=Config(s3={"addressing_style": addressing_style}),
    )
    client.head_bucket(Bucket=settings.S3_BUCKET_NAME)


class LiveHealthView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        return Response({"status": "ok"})


class ReadyHealthView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        checks = {
            "database": check_database,
            "redis": check_redis,
            "object_storage": check_object_storage,
        }
        results = {}
        for name, check in checks.items():
            try:
                check()
            except Exception:  # noqa: BLE001 - readiness must collapse every provider failure.
                results[name] = "error"
            else:
                results[name] = "ok"

        is_ready = all(result == "ok" for result in results.values())
        response_status = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
        return Response(
            {"status": "ok" if is_ready else "error", "checks": results},
            status=response_status,
        )
