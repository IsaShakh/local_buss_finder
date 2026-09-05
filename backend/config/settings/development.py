from config.sentry import init_backend_sentry

from .base import *

SENTRY_ENABLED = init_backend_sentry(SENTRY_DSN)

DEBUG = True
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
]
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS
