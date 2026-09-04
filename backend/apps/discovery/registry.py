from collections.abc import Callable
from functools import cache
from typing import cast

from django.conf import settings
from django.utils.module_loading import import_string

from .domain import DiscoveryAdapter
from .errors import UnknownDiscoveryAdapter

AdapterFactory = Callable[[], DiscoveryAdapter]


@cache
def _load_factory(dotted_path: str) -> AdapterFactory:
    return cast(AdapterFactory, import_string(dotted_path))


def get_adapter(source_code: str) -> DiscoveryAdapter:
    try:
        dotted_path = settings.DISCOVERY_ADAPTERS[source_code]
    except KeyError as error:
        raise UnknownDiscoveryAdapter(source_code) from error
    return _load_factory(dotted_path)()
