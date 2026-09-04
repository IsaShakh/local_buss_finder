import json
from collections.abc import Sequence

from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Polygon

ALANYA_PILOT_BBOX = (31.70, 36.30, 32.65, 36.75)


def multipolygon_from_bbox(bbox: Sequence[float]) -> MultiPolygon:
    return MultiPolygon(Polygon.from_bbox(tuple(bbox)), srid=4326)


def geometry_bbox(geometry: GEOSGeometry) -> list[float]:
    return [float(value) for value in geometry.extent]


def geometry_geojson(geometry: GEOSGeometry) -> dict:
    return json.loads(geometry.geojson)
