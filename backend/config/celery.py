import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("local_business_intelligence")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

from common import celery_signals  # noqa: F401
