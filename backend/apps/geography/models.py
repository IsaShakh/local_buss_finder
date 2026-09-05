from typing import ClassVar

from django.contrib.gis.db import models as gis_models
from django.contrib.postgres.indexes import GistIndex
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

from common.models import TimestampedUUIDModel

country_code_validator = RegexValidator(
    regex=r"^[A-Z]{2}$",
    message="Код страны должен состоять из двух заглавных латинских букв.",
)


class Country(TimestampedUUIDModel):
    code = models.CharField(max_length=2, unique=True, validators=[country_code_validator])
    name = models.CharField(max_length=255)
    name_ru = models.CharField(max_length=255)
    geometry = gis_models.MultiPolygonField(
        srid=4326,
        null=True,
        blank=True,
        spatial_index=False,
    )

    class Meta:
        ordering = ("name_ru", "name")

    def __str__(self) -> str:
        return self.name_ru


class Province(TimestampedUUIDModel):
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="provinces")
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    name_ru = models.CharField(max_length=255)
    geometry = gis_models.MultiPolygonField(
        srid=4326,
        null=True,
        blank=True,
        spatial_index=False,
    )

    class Meta:
        ordering = ("name_ru", "name")
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=("country", "code"),
                name="geography_province_country_code_uniq",
            )
        ]

    def __str__(self) -> str:
        return self.name_ru


class District(TimestampedUUIDModel):
    province = models.ForeignKey(Province, on_delete=models.CASCADE, related_name="districts")
    slug = models.SlugField(max_length=120)
    name = models.CharField(max_length=255)
    name_ru = models.CharField(max_length=255)
    geometry = gis_models.MultiPolygonField(
        srid=4326,
        null=True,
        blank=True,
        spatial_index=False,
    )

    class Meta:
        ordering = ("name_ru", "name")
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=("province", "slug"),
                name="geography_district_province_slug_uniq",
            )
        ]

    def __str__(self) -> str:
        return self.name_ru


class Neighborhood(TimestampedUUIDModel):
    district = models.ForeignKey(
        District,
        on_delete=models.CASCADE,
        related_name="neighborhoods",
    )
    slug = models.SlugField(max_length=120)
    name = models.CharField(max_length=255)
    name_ru = models.CharField(max_length=255)
    geometry = gis_models.MultiPolygonField(
        srid=4326,
        null=True,
        blank=True,
        spatial_index=False,
    )

    class Meta:
        ordering = ("name_ru", "name")
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=("district", "slug"),
                name="geography_neighborhood_district_slug_uniq",
            )
        ]

    def __str__(self) -> str:
        return self.name_ru


class SearchArea(TimestampedUUIDModel):
    name = models.CharField(max_length=255)
    country = models.ForeignKey(Country, on_delete=models.PROTECT, related_name="search_areas")
    province = models.ForeignKey(
        Province,
        on_delete=models.PROTECT,
        related_name="search_areas",
        null=True,
        blank=True,
    )
    district = models.ForeignKey(
        District,
        on_delete=models.PROTECT,
        related_name="search_areas",
        null=True,
        blank=True,
    )
    neighborhood = models.ForeignKey(
        Neighborhood,
        on_delete=models.PROTECT,
        related_name="search_areas",
        null=True,
        blank=True,
    )
    geometry = gis_models.MultiPolygonField(srid=4326, spatial_index=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name", "id")
        indexes: ClassVar = [GistIndex(fields=("geometry",), name="geo_searcharea_geom_gist")]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}

        if self.province_id and self.province.country_id != self.country_id:
            errors["province"] = "Провинция не относится к выбранной стране."

        if self.district_id and (
            not self.province_id or self.district.province_id != self.province_id
        ):
            errors["district"] = "Район не относится к выбранной провинции."

        if self.neighborhood_id and (
            not self.district_id or self.neighborhood.district_id != self.district_id
        ):
            errors["neighborhood"] = "Микрорайон не относится к выбранному району."

        if self.geometry is None or self.geometry.empty:
            errors["geometry"] = "Геометрия не может быть пустой."
        elif self.geometry.srid != 4326:
            errors["geometry"] = "Геометрия должна использовать SRID 4326."
        elif not self.geometry.valid:
            errors["geometry"] = "Геометрия должна быть валидной."

        if errors:
            raise ValidationError(errors)
