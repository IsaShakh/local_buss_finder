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
    "apps.geography.apps.GeographyConfig",
    "apps.system.apps.SystemConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]

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

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
