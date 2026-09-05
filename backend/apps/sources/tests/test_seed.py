import pytest
from django.core.management import call_command

from apps.sources.models import Source


@pytest.mark.django_db
def test_source_seed_is_idempotent():
    call_command("seed_sources")
    call_command("seed_sources")

    assert Source.objects.count() == 2
    assert set(Source.objects.values_list("code", flat=True)) == {"overture", "osm"}


@pytest.mark.django_db
def test_source_seed_preserves_manually_disabled_source():
    call_command("seed_sources")
    Source.objects.filter(code="osm").update(is_active=False)

    call_command("seed_sources")

    assert Source.objects.get(code="osm").is_active is False


@pytest.mark.django_db
def test_source_seed_can_explicitly_reset_active_state():
    call_command("seed_sources")
    Source.objects.filter(code="osm").update(is_active=False)

    call_command("seed_sources", reset_active=True)

    assert Source.objects.get(code="osm").is_active is True


@pytest.mark.django_db
def test_source_seed_creates_expected_public_metadata():
    call_command("seed_sources")

    overture = Source.objects.get(code="overture")
    osm = Source.objects.get(code="osm")
    assert (overture.name, overture.source_type, overture.license_code) == (
        "Overture Maps",
        "open_data",
        "CDLA-Permissive-2.0/Apache-2.0",
    )
    assert (osm.name, osm.attribution, osm.license_code, osm.concurrency) == (
        "OpenStreetMap",
        "© OpenStreetMap contributors",
        "ODbL-1.0",
        1,
    )
