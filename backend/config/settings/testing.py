from .base import *

ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1", "backend", "nginx"]
CSRF_TRUSTED_ORIGINS = ["http://127.0.0.1:8081"]
SENTRY_DSN = ""
SENTRY_ENABLED = False
CELERY_TASK_ALWAYS_EAGER = False

DISCOVERY_USE_FIXTURES = env.bool("DISCOVERY_USE_FIXTURES", default=False)
E2E_FIXTURE_CREDENTIALS = (
    env.bool("E2E_FIXTURE_CREDENTIALS", default=False) if DISCOVERY_USE_FIXTURES else False
)
if DISCOVERY_USE_FIXTURES:
    DISCOVERY_ADAPTERS = {
        "overture": "apps.discovery.tests.fake_adapter.FixtureOvertureAdapter",
        "osm": "apps.discovery.tests.fake_adapter.FixtureOsmAdapter",
    }
