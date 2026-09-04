from .base import *

DEBUG = True
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = ["http://localhost:5173", "http://localhost:8080"]
CSRF_TRUSTED_ORIGINS = ["http://localhost:5173", "http://localhost:8080"]
