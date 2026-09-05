import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.discovery.config import validate_live_osm_configuration


@pytest.mark.parametrize(
    ("values", "expected_setting"),
    [
        (
            {
                "overpass_url": "",
                "dataset_version": "snapshot-1",
                "source_user_agent": "lbi/0.1 (+mailto:data@acme.io)",
            },
            "OVERPASS_URL",
        ),
        (
            {
                "overpass_url": "https://overpass.acme.io/api/interpreter",
                "dataset_version": "",
                "source_user_agent": "lbi/0.1 (+mailto:data@acme.io)",
            },
            "OSM_DATASET_VERSION",
        ),
        (
            {
                "overpass_url": "https://overpass.invalid/api/interpreter",
                "dataset_version": "snapshot-1",
                "source_user_agent": "lbi/0.1 (+mailto:data@acme.io)",
            },
            "OVERPASS_URL",
        ),
        (
            {
                "overpass_url": "https://overpass.example/api/interpreter",
                "dataset_version": "snapshot-1",
                "source_user_agent": "lbi/0.1 (+mailto:data@acme.io)",
            },
            "OVERPASS_URL",
        ),
        (
            {
                "overpass_url": "https://localhost/api/interpreter",
                "dataset_version": "snapshot-1",
                "source_user_agent": "lbi/0.1 (+mailto:data@acme.io)",
            },
            "OVERPASS_URL",
        ),
        (
            {
                "overpass_url": "https://overpass.acme.io/api/interpreter",
                "dataset_version": "snapshot-1",
                "source_user_agent": "local-business-intelligence/0.1",
            },
            "SOURCE_USER_AGENT",
        ),
        (
            {
                "overpass_url": "https://overpass.acme.io/api/interpreter",
                "dataset_version": "snapshot-1",
                "source_user_agent": "https://acme.io/contact",
            },
            "SOURCE_USER_AGENT",
        ),
        (
            {
                "overpass_url": "https://overpass.acme.io/api/interpreter",
                "dataset_version": "snapshot-1",
                "source_user_agent": "lbi/0.1 (+https://example.invalid/contact)",
            },
            "SOURCE_USER_AGENT",
        ),
    ],
)
def test_live_osm_configuration_rejects_unsafe_values(values, expected_setting):
    with pytest.raises(ImproperlyConfigured, match=expected_setting):
        validate_live_osm_configuration(**values)


def test_live_osm_configuration_accepts_https_endpoint_and_real_contact_uri():
    validate_live_osm_configuration(
        overpass_url="https://overpass.acme.io/api/interpreter",
        dataset_version="replication-sequence-12345",
        source_user_agent="local-business-intelligence/0.1 (+https://acme.io/contact)",
    )


def test_production_settings_reject_placeholder_source_user_agent():
    environment = {
        **os.environ,
        "DJANGO_SECRET_KEY": "production-test-key-with-at-least-32-characters",
        "DJANGO_ALLOWED_HOSTS": "lbi.example.test",
        "DJANGO_CORS_ALLOWED_ORIGINS": "https://lbi.example.test",
        "DJANGO_CSRF_TRUSTED_ORIGINS": "https://lbi.example.test",
        "DATABASE_URL": "postgis://lbi:test@postgres:5432/lbi",
        "REDIS_URL": "redis://redis:6379/0",
        "S3_ENDPOINT_URL": "https://s3.example.test",
        "S3_ACCESS_KEY_ID": "test-access-key",
        "S3_SECRET_ACCESS_KEY": "test-secret-key",
        "S3_BUCKET_NAME": "lbi-production-test",
        "OVERPASS_URL": "https://overpass.example.test/api/interpreter",
        "OSM_DATASET_VERSION": "2026-08-snapshot",
        "SOURCE_USER_AGENT": ("local-business-intelligence/0.1 (+https://example.invalid/contact)"),
    }

    result = subprocess.run(
        [sys.executable, "manage.py", "check", "--settings=config.settings.production"],
        cwd=Path(__file__).resolve().parents[3],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "SOURCE_USER_AGENT" in result.stdout + result.stderr
