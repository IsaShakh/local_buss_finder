from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.sources.models import Source


@pytest.mark.django_db
def test_source_persists_operational_limits_with_safe_defaults():
    source = Source.objects.create(
        code="osm",
        name="OpenStreetMap",
        source_type=Source.Type.OPEN_DATA,
        attribution="© OpenStreetMap contributors",
        license_code="ODbL-1.0",
        requests_per_second=Decimal("0.20"),
        concurrency=1,
        timeout_seconds=60,
        max_retries=3,
    )

    assert source.requests_per_second == Decimal("0.20")
    assert source.concurrency == 1
    assert source.timeout_seconds == 60
    assert source.max_retries == 3
    assert source.is_paid is False
    assert source.is_active is True
    assert source.settings == {}
    assert source.request_count == 0
    assert source.total_cost == Decimal(0)


@pytest.mark.django_db
def test_source_code_is_unique():
    required = {
        "source_type": Source.Type.OPEN_DATA,
        "attribution": "fixture",
        "license_code": "fixture-only",
    }
    Source.objects.create(code="osm", name="OpenStreetMap", **required)

    with pytest.raises(IntegrityError), transaction.atomic():
        Source.objects.create(code="osm", name="Duplicate", **required)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("settings", "forbidden_key"),
    [
        ({"nested": {"api_token": "must-not-be-stored"}}, "api_token"),
        ({"clientSecret": "must-not-be-stored"}, "clientSecret"),
        ({"items": [{"PASSWORD_hint": "must-not-be-stored"}]}, "PASSWORD_hint"),
        ({"provider_api_key_name": "must-not-be-stored"}, "provider_api_key_name"),
    ],
)
def test_source_rejects_secret_like_settings_keys(settings, forbidden_key):
    source = Source(
        code="unsafe",
        name="Unsafe",
        source_type=Source.Type.OPEN_DATA,
        attribution="fixture",
        license_code="fixture-only",
        settings=settings,
    )

    with pytest.raises(ValidationError, match=forbidden_key):
        source.full_clean()
