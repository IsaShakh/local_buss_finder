import pytest

from apps.discovery.domain import BoundingBox
from apps.discovery.osm_query import (
    InvalidSelector,
    build_overpass_query,
)


def test_query_builder_uses_selected_mappings_and_bounded_resources():
    query = build_overpass_query(
        bbox=BoundingBox(west=31.70, south=36.30, east=32.65, north=36.75),
        selectors=("amenity=dentist", "tourism=hotel"),
        timeout_seconds=60,
        max_size_bytes=268_435_456,
    )

    assert query == (
        "[out:json][timeout:60][maxsize:268435456];"
        '(nwr["amenity"="dentist"](36.3,31.7,36.75,32.65);'
        'nwr["tourism"="hotel"](36.3,31.7,36.75,32.65););'
        "out center tags;"
    )


@pytest.mark.parametrize(
    "selector",
    ['amenity=dentist";out;', "amenity=dentist\nnode(0,0,1,1)", "amenity"],
)
def test_query_builder_rejects_selector_injection(selector):
    with pytest.raises(InvalidSelector):
        build_overpass_query(
            bbox=BoundingBox(31.70, 36.30, 32.65, 36.75),
            selectors=(selector,),
            timeout_seconds=60,
            max_size_bytes=268_435_456,
        )


def test_query_builder_accepts_only_documented_selector_alphabet():
    query = build_overpass_query(
        bbox=BoundingBox(31.70, 36.30, 32.65, 36.75),
        selectors=("contact:healthcare=dentist-clinic",),
        timeout_seconds=60,
        max_size_bytes=268_435_456,
    )

    assert '["contact:healthcare"="dentist-clinic"]' in query


@pytest.mark.parametrize("field", ["selectors", "timeout_seconds", "max_size_bytes"])
def test_query_builder_rejects_empty_or_unbounded_resources(field):
    arguments = {
        "bbox": BoundingBox(31.70, 36.30, 32.65, 36.75),
        "selectors": ("amenity=dentist",),
        "timeout_seconds": 60,
        "max_size_bytes": 268_435_456,
    }
    arguments[field] = () if field == "selectors" else 0

    with pytest.raises(ValueError):
        build_overpass_query(**arguments)
