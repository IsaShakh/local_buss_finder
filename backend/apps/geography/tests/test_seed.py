import pytest
from django.core.management import call_command

from apps.geography.models import Country, District, Province, SearchArea


@pytest.mark.django_db
def test_reference_seed_is_idempotent():
    call_command("seed_reference_data")
    call_command("seed_reference_data")

    assert Country.objects.filter(code="TR").count() == 1
    assert Province.objects.filter(country__code="TR", code="07").count() == 1
    assert District.objects.filter(province__code="07", slug="alanya").count() == 1
    assert SearchArea.objects.filter(name="Аланья — пилот", is_active=True).count() == 1


@pytest.mark.django_db
def test_reference_seed_creates_alanya_operational_bbox():
    call_command("seed_reference_data")

    area = SearchArea.objects.get(name="Аланья — пилот")
    assert list(area.geometry.extent) == [31.7, 36.3, 32.65, 36.75]
