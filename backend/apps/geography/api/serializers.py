from rest_framework import serializers

from apps.geography.models import Country, District, Neighborhood, Province, SearchArea
from apps.geography.services import geometry_bbox, geometry_geojson


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ("id", "code", "name", "name_ru")


class ProvinceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Province
        fields = ("id", "code", "name", "name_ru")


class DistrictSerializer(serializers.ModelSerializer):
    class Meta:
        model = District
        fields = ("id", "slug", "name", "name_ru")


class NeighborhoodSerializer(serializers.ModelSerializer):
    class Meta:
        model = Neighborhood
        fields = ("id", "slug", "name", "name_ru")


class SearchAreaSerializer(serializers.ModelSerializer):
    country = CountrySerializer(read_only=True)
    province = ProvinceSerializer(read_only=True)
    district = DistrictSerializer(read_only=True)
    neighborhood = NeighborhoodSerializer(read_only=True)
    geometry = serializers.SerializerMethodField()
    bbox = serializers.SerializerMethodField()

    class Meta:
        model = SearchArea
        fields = (
            "id",
            "name",
            "country",
            "province",
            "district",
            "neighborhood",
            "geometry",
            "bbox",
        )

    def get_geometry(self, obj: SearchArea) -> dict:
        return geometry_geojson(obj.geometry)

    def get_bbox(self, obj: SearchArea) -> list[float]:
        return geometry_bbox(obj.geometry)
