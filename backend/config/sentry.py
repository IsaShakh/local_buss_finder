from copy import deepcopy

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration


def sanitize_sentry_event(event: dict, hint: dict) -> dict:
    safe = deepcopy(event)
    request = safe.get("request")
    if isinstance(request, dict):
        for field in ("headers", "cookies", "data", "body", "env"):
            request.pop(field, None)
    safe.pop("user", None)
    return safe


def init_backend_sentry(dsn: str) -> bool:
    if not dsn.strip():
        return False
    sentry_sdk.init(
        dsn=dsn,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        send_default_pii=False,
        before_send=sanitize_sentry_event,
    )
    return True
