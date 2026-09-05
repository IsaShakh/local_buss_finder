import pytest
from django.contrib.gis.geos import MultiPolygon, Polygon
from django.core.exceptions import ValidationError
from django.db import connection

from apps.geography.models import Country, District, Neighborhood, Province, SearchArea


def alanya_geometry() -> MultiPolygon:
    return MultiPolygon(
        Polygon.from_bbox((31.70, 36.30, 32.65, 36.75)),
        srid=4326,
    )


@pytest.mark.django_db
def test_search_area_accepts_consistent_hierarchy_and_4326_geometry():
    country = Country.objects.create(code="TR", name="Türkiye", name_ru="Турция")
    province = Province.objects.create(
        country=country,
        code="07",
        name="Antalya",
        name_ru="Анталья",
    )
    district = District.objects.create(
        province=province,
        slug="alanya",
        name="Alanya",
        name_ru="Аланья",
    )

    area = SearchArea(
        name="Аланья — пилот",
        country=country,
        province=province,
        district=district,
        geometry=alanya_geometry(),
    )
    area.full_clean()
    area.save()

    assert area.geometry.srid == 4326
    assert area.is_active is True


@pytest.mark.django_db
def test_search_area_rejects_mismatched_district_ancestry():
    country = Country.objects.create(code="TR", name="Türkiye", name_ru="Турция")
    antalya = Province.objects.create(
        country=country,
        code="07",
        name="Antalya",
        name_ru="Анталья",
    )
    mugla = Province.objects.create(
        country=country,
        code="48",
        name="Muğla",
        name_ru="Мугла",
    )
    mismatched_district = District.objects.create(
        province=mugla,
        slug="bodrum",
        name="Bodrum",
        name_ru="Бодрум",
    )
    area = SearchArea(
        name="Некорректная область",
        country=country,
        province=antalya,
        district=mismatched_district,
        geometry=alanya_geometry(),
    )

    with pytest.raises(
        ValidationError,
        match="Район не относится к выбранной провинции",
    ):
        area.full_clean()


@pytest.mark.django_db
def test_search_area_rejects_mismatched_province_ancestry():
    turkey = Country.objects.create(code="TR", name="Türkiye", name_ru="Турция")
    greece = Country.objects.create(code="GR", name="Greece", name_ru="Греция")
    antalya = Province.objects.create(
        country=turkey,
        code="07",
        name="Antalya",
        name_ru="Анталья",
    )
    alanya = District.objects.create(
        province=antalya,
        slug="alanya",
        name="Alanya",
        name_ru="Аланья",
    )
    wrong_country = SearchArea(
        name="Неверная страна",
        country=greece,
        province=antalya,
        district=alanya,
        geometry=alanya_geometry(),
    )
    with pytest.raises(
        ValidationError,
        match="Провинция не относится к выбранной стране",
    ):
        wrong_country.full_clean()


@pytest.mark.django_db
def test_search_area_rejects_mismatched_neighborhood_ancestry():
    turkey = Country.objects.create(code="TR", name="Türkiye", name_ru="Турция")
    antalya = Province.objects.create(
        country=turkey,
        code="07",
        name="Antalya",
        name_ru="Анталья",
    )
    alanya = District.objects.create(
        province=antalya,
        slug="alanya",
        name="Alanya",
        name_ru="Аланья",
    )
    kemer = District.objects.create(
        province=antalya,
        slug="kemer",
        name="Kemer",
        name_ru="Кемер",
    )
    neighborhood = Neighborhood.objects.create(
        district=kemer,
        slug="merkez",
        name="Merkez",
        name_ru="Центр",
    )
    wrong_neighborhood = SearchArea(
        name="Неверный микрорайон",
        country=turkey,
        province=antalya,
        district=alanya,
        neighborhood=neighborhood,
        geometry=alanya_geometry(),
    )
    with pytest.raises(
        ValidationError,
        match="Микрорайон не относится к выбранному району",
    ):
        wrong_neighborhood.full_clean()


@pytest.mark.django_db
def test_search_area_rejects_empty_geometry():
    country = Country.objects.create(code="TR", name="Türkiye", name_ru="Турция")
    province = Province.objects.create(
        country=country,
        code="07",
        name="Antalya",
        name_ru="Анталья",
    )
    district = District.objects.create(
        province=province,
        slug="alanya",
        name="Alanya",
        name_ru="Аланья",
    )
    area = SearchArea(
        name="Пустая область",
        country=country,
        province=province,
        district=district,
        geometry=MultiPolygon(srid=4326),
    )

    with pytest.raises(ValidationError, match="Геометрия не может быть пустой"):
        area.full_clean()


@pytest.mark.django_db
def test_search_area_rejects_non_4326_geometry():
    country = Country.objects.create(code="TR", name="Türkiye", name_ru="Турция")
    area = SearchArea(
        name="Неверная проекция",
        country=country,
        geometry=MultiPolygon(
            Polygon.from_bbox((31.70, 36.30, 32.65, 36.75)),
            srid=3857,
        ),
    )

    with pytest.raises(ValidationError, match="Геометрия должна использовать SRID 4326"):
        area.full_clean()


@pytest.mark.django_db
def test_search_area_rejects_topologically_invalid_geometry():
    country = Country.objects.create(code="TR", name="Türkiye", name_ru="Турция")
    self_intersecting = Polygon(
        (
            (31.70, 36.30),
            (32.65, 36.75),
            (32.65, 36.30),
            (31.70, 36.75),
            (31.70, 36.30),
        ),
        srid=4326,
    )
    area = SearchArea(
        name="Невалидная область",
        country=country,
        geometry=MultiPolygon(self_intersecting, srid=4326),
    )

    with pytest.raises(ValidationError, match="Геометрия должна быть валидной"):
        area.full_clean()


@pytest.mark.django_db
def test_required_postgres_extensions_are_installed():
    with connection.cursor() as cursor:
        cursor.execute("SELECT extname FROM pg_extension")
        names = {row[0] for row in cursor.fetchall()}

    assert {"postgis", "pg_trgm", "unaccent"}.issubset(names)
