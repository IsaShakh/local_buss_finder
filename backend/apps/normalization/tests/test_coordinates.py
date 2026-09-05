import pytest

from apps.normalization.rules.coordinates import InvalidCoordinates, normalize_coordinates


@pytest.mark.parametrize(("longitude", "latitude"), [(181, 36), (32, 91)])
def test_invalid_coordinates_are_rejected(longitude, latitude):
    with pytest.raises(InvalidCoordinates):
        normalize_coordinates(longitude, latitude)
