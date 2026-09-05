import pytest
from django.core.management import call_command
from django.db import IntegrityError, transaction

from apps.taxonomy.models import BusinessCategory, SourceCategoryMapping
from apps.taxonomy.services import resolve_category, resolve_external_categories


def create_dentist_mapping(osm_source):
    root = BusinessCategory.objects.create(name="Медицина", slug="health")
    dentist = BusinessCategory.objects.create(name="Стоматология", slug="dentist", parent=root)
    mapping = SourceCategoryMapping.objects.create(
        source=osm_source,
        external_category="amenity=dentist",
        category=dentist,
    )
    return dentist, mapping


@pytest.mark.django_db
def test_resolve_category_returns_internal_leaf_for_osm_tag(osm_source):
    dentist, _ = create_dentist_mapping(osm_source)

    assert resolve_category(osm_source.id, "amenity=dentist") == dentist.id


@pytest.mark.django_db
def test_unknown_category_returns_none(osm_source):
    assert resolve_category(osm_source.id, "shop=unknown") is None


@pytest.mark.django_db
def test_empty_selection_expands_all_active_mappings_for_source(osm_source):
    call_command("seed_taxonomy")

    assert resolve_external_categories(osm_source.id, ()) == (
        "amenity=dentist",
        "office=estate_agent",
        "shop=beauty",
        "tourism=hotel",
    )


@pytest.mark.django_db
def test_nonempty_selection_expands_only_selected_categories_for_source(osm_source):
    call_command("seed_taxonomy")
    dentist = BusinessCategory.objects.get(slug="dentist")

    assert resolve_external_categories(osm_source.id, (dentist.id,)) == ("amenity=dentist",)


@pytest.mark.django_db
@pytest.mark.parametrize("inactive_target", ["source", "mapping", "category"])
def test_resolve_category_ignores_inactive_configuration(osm_source, inactive_target):
    dentist, mapping = create_dentist_mapping(osm_source)
    target = {"source": osm_source, "mapping": mapping, "category": dentist}[inactive_target]
    target.is_active = False
    target.save(update_fields=("is_active",))

    assert resolve_category(osm_source.id, "amenity=dentist") is None


@pytest.mark.django_db
@pytest.mark.parametrize("inactive_target", ["source", "mapping", "category"])
def test_external_category_expansion_ignores_inactive_configuration(
    osm_source,
    inactive_target,
):
    dentist, mapping = create_dentist_mapping(osm_source)
    target = {"source": osm_source, "mapping": mapping, "category": dentist}[inactive_target]
    target.is_active = False
    target.save(update_fields=("is_active",))

    assert resolve_external_categories(osm_source.id, ()) == ()


@pytest.mark.django_db
def test_external_category_is_unique_within_source(osm_source):
    dentist, _ = create_dentist_mapping(osm_source)

    with pytest.raises(IntegrityError), transaction.atomic():
        SourceCategoryMapping.objects.create(
            source=osm_source,
            external_category="amenity=dentist",
            category=dentist,
        )
