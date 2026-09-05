from apps.normalization.domain import GeoPoint


class InvalidCoordinates(ValueError):
    pass


def normalize_coordinates(longitude: float, latitude: float) -> GeoPoint:
    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        raise InvalidCoordinates
    return GeoPoint(longitude=float(longitude), latitude=float(latitude))
