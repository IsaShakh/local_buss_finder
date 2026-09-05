from collections.abc import Callable
from functools import cache
from typing import cast

from django.conf import settings
from django.utils.module_loading import import_string

from .domain import DiscoveryAdapter
from .errors import UnknownDiscoveryAdapter

AdapterFactory = Callable[[], DiscoveryAdapter]
TEST_ADAPTER_PREFIX = "apps.discovery.tests."


@cache
def _load_factory(dotted_path: str) -> AdapterFactory:
    return cast(AdapterFactory, import_string(dotted_path))


def get_adapter(source_code: str) -> DiscoveryAdapter:
    try:
        dotted_path = settings.DISCOVERY_ADAPTERS[source_code]
    except KeyError as error:
        raise UnknownDiscoveryAdapter(source_code) from error
    if dotted_path.startswith(TEST_ADAPTER_PREFIX) and not getattr(
        settings, "DISCOVERY_USE_FIXTURES", False
    ):
        raise UnknownDiscoveryAdapter(source_code)
    return _load_factory(dotted_path)()
