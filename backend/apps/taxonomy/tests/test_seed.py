import pytest
from django.core.management import call_command

from apps.taxonomy.models import BusinessCategory, SourceCategoryMapping


@pytest.mark.django_db
def test_taxonomy_seed_is_idempotent(osm_source, overture_source):
    assert {osm_source.code, overture_source.code} == {"osm", "overture"}
    call_command("seed_taxonomy")
    call_command("seed_taxonomy")

    assert BusinessCategory.objects.count() == 8
    assert SourceCategoryMapping.objects.count() == 8


@pytest.mark.django_db
def test_taxonomy_seed_creates_exact_provider_mappings(osm_source, overture_source):
    assert {osm_source.code, overture_source.code} == {"osm", "overture"}
    call_command("seed_taxonomy")

    mappings = tuple(
        SourceCategoryMapping.objects.order_by("source__code", "external_category").values_list(
            "source__code",
            "external_category",
            "category__slug",
        )
    )
    assert mappings == (
        ("osm", "amenity=dentist", "dentist"),
        ("osm", "office=estate_agent", "real-estate-agency"),
        ("osm", "shop=beauty", "beauty-salon"),
        ("osm", "tourism=hotel", "hotel"),
        ("overture", "beauty_salon", "beauty-salon"),
        ("overture", "dentist", "dentist"),
        ("overture", "hotel", "hotel"),
        ("overture", "real_estate_agent", "real-estate-agency"),
    )
