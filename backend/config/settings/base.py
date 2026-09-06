import environ

BASE_DIR = environ.Path(__file__) - 3
env = environ.Env()

SECRET_KEY = env("DJANGO_SECRET_KEY", default="unsafe-dev-only-change-me")
DEBUG = False
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.gis",
    "django.contrib.postgres",
    "django.contrib.sessions",
    "corsheaders",
    "rest_framework",
    "apps.deduplication.apps.DeduplicationConfig",
    "apps.businesses.apps.BusinessesConfig",
    "apps.campaigns.apps.CampaignsConfig",
    "apps.discovery.apps.DiscoveryConfig",
    "apps.geography.apps.GeographyConfig",
    "apps.normalization.apps.NormalizationConfig",
    "apps.sources.apps.SourcesConfig",
    "apps.system.apps.SystemConfig",
    "apps.taxonomy.apps.TaxonomyConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.system.middleware.CorrelationIdMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]

CSRF_FAILURE_VIEW = "apps.system.api.csrf.csrf_failure"

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgis://lbi:lbi-dev-only@postgres:5432/local_business_intelligence",
        engine="django.contrib.gis.db.backends.postgis",
    )
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL", default="redis://redis:6379/0"),
    }
}

CELERY_TASK_ROUTES = {
    "apps.discovery.tasks.*": {"queue": "discovery"},
    "apps.normalization.tasks.*": {"queue": "normalization"},
}
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_PUBLISH_RETRY = True
CELERY_TASK_PUBLISH_RETRY_POLICY = {
    "max_retries": 3,
    "interval_start": 0,
    "interval_step": 0.5,
    "interval_max": 1,
}
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=env("REDIS_URL"))
CELERY_TASK_IGNORE_RESULT = env.bool("CELERY_TASK_IGNORE_RESULT", default=True)
CELERY_RESULT_BACKEND = None

DISCOVERY_ADAPTERS = {
    "osm": "apps.discovery.adapters.osm.OpenStreetMapAdapter",
    "overture": "apps.discovery.adapters.overture.OvertureAdapter",
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "EXCEPTION_HANDLER": "apps.system.api.exceptions.api_exception_handler",
    "PAGE_SIZE": 50,
}

S3_ENDPOINT_URL = env("S3_ENDPOINT_URL", default="http://garage:3900")
S3_ACCESS_KEY_ID = env("S3_ACCESS_KEY_ID")
S3_SECRET_ACCESS_KEY = env("S3_SECRET_ACCESS_KEY")
S3_BUCKET_NAME = env("S3_BUCKET_NAME", default="local-business-intelligence")
S3_REGION_NAME = env("S3_REGION_NAME", default="garage")
S3_FORCE_PATH_STYLE = env.bool("S3_FORCE_PATH_STYLE", default=True)

OVERPASS_URL = env("OVERPASS_URL", default="")
OSM_DATASET_VERSION = env("OSM_DATASET_VERSION", default="")
SOURCE_USER_AGENT = env(
    "SOURCE_USER_AGENT",
    default="local-business-intelligence/0.1 (+https://example.invalid/contact)",
)

SENTRY_DSN = env("SENTRY_DSN", default="")
SENTRY_ENABLED = False

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "common.observability.StructuredJsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "stream": "ext://sys.stdout",
        }
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
