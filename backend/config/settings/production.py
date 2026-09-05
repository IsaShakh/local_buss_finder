from apps.discovery.config import validate_live_osm_configuration
from config.sentry import init_backend_sentry

from .base import *

SENTRY_ENABLED = init_backend_sentry(SENTRY_DSN)

validate_live_osm_configuration(
    overpass_url=OVERPASS_URL,
    dataset_version=OSM_DATASET_VERSION,
    source_user_agent=SOURCE_USER_AGENT,
)

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = env.list("DJANGO_CORS_ALLOWED_ORIGINS")
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS")
