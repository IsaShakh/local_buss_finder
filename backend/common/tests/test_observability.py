import importlib
import json
import logging
import sys
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
import sentry_sdk
from django.conf import settings

from common.celery_signals import log_task_postrun, log_task_prerun
from common.observability import (
    STRUCTURED_FIELDS,
    StructuredJsonFormatter,
    sanitize_log_context,
    structured_event,
)
from config.sentry import init_backend_sentry, sanitize_sentry_event


def test_structured_context_drops_secrets_payload_and_contacts(caplog):
    caplog.set_level(logging.INFO, logger="common.observability")

    structured_event(
        "source_record.stored",
        campaign_id="campaign-id",
        source="osm",
        password="secret",
        authorization="Bearer token",
        raw_payload={"phone": "+905321234567"},
        email="person@example.test",
    )

    rendered = caplog.records[-1].getMessage()
    payload = json.loads(rendered)
    assert set(payload) == set(STRUCTURED_FIELDS)
    assert payload["campaign_id"] == "campaign-id"
    for forbidden in ("secret", "Bearer", "+905321234567", "person@example.test"):
        assert forbidden not in rendered


def test_structured_context_keeps_only_scalar_allowlisted_values():
    identifier = uuid4()
    happened_at = datetime(2026, 9, 4, 10, 30, tzinfo=UTC)

    safe = sanitize_log_context(
        {
            "campaign_id": identifier,
            "duration_ms": 12.5,
            "message": "completed",
            "source": {"code": "osm"},
            "raw_payload": "forbidden",
            "timestamp": happened_at,
        }
    )

    assert safe == {
        "campaign_id": str(identifier),
        "duration_ms": 12.5,
        "message": "completed",
        "timestamp": happened_at.isoformat(),
    }


def test_structured_formatter_keeps_exact_top_level_contract():
    payload = dict.fromkeys(STRUCTURED_FIELDS)
    payload.update(
        {
            "timestamp": "2026-09-04T10:30:00+00:00",
            "level": "info",
            "service": "backend",
            "event": "campaign.finished",
            "message": "Campaign finished",
        }
    )
    record = logging.LogRecord(
        name="common.observability",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=json.dumps(payload),
        args=(),
        exc_info=None,
    )

    rendered = json.loads(StructuredJsonFormatter().format(record))

    assert rendered == payload


def test_backend_sentry_is_disabled_for_empty_dsn(monkeypatch):
    calls = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **kwargs: calls.append(kwargs))

    assert init_backend_sentry("") is False
    assert calls == []


def test_backend_sentry_is_private_by_default(monkeypatch):
    calls = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **kwargs: calls.append(kwargs))

    assert init_backend_sentry("https://public@example.test/1") is True
    assert calls[0]["send_default_pii"] is False
    assert calls[0]["before_send"] is sanitize_sentry_event
    assert len(calls[0]["integrations"]) == 2


def test_testing_settings_import_never_initializes_sentry(monkeypatch):
    calls = []
    original_modules = {
        name: sys.modules.get(name) for name in ("config.settings.base", "config.settings.testing")
    }
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.test/1")
    monkeypatch.setattr(sentry_sdk, "init", lambda **kwargs: calls.append(kwargs))

    try:
        for name in original_modules:
            sys.modules.pop(name, None)
        testing_settings = importlib.import_module("config.settings.testing")
    finally:
        for name, module in original_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    assert testing_settings.SENTRY_DSN == ""
    assert testing_settings.SENTRY_ENABLED is False
    assert calls == []


def test_structured_logging_writes_to_stdout():
    assert settings.LOGGING["handlers"]["console"]["stream"] == "ext://sys.stdout"


def test_sentry_sanitizer_drops_request_secrets_and_user_identifiers():
    event = {
        "request": {
            "headers": {"authorization": "Bearer token"},
            "cookies": {"sessionid": "secret"},
            "data": {"password": "secret"},
            "url": "https://example.test/safe-path",
        },
        "user": {"id": "42", "ip_address": "127.0.0.1", "email": "person@example.test"},
        "message": "safe failure",
    }

    safe = sanitize_sentry_event(event, {})

    assert safe["request"] == {"url": "https://example.test/safe-path"}
    assert "user" not in safe
    assert safe["message"] == "safe failure"


@pytest.mark.parametrize(
    ("headers", "expected_correlation_id"),
    [({"correlation_id": "campaign-ui-42"}, "campaign-ui-42"), ({}, "task-42")],
)
def test_celery_lifecycle_uses_header_or_task_id(
    monkeypatch,
    headers,
    expected_correlation_id,
):
    events = []
    task = SimpleNamespace(request=SimpleNamespace(headers=headers))
    monkeypatch.setattr(
        "common.celery_signals.structured_event",
        lambda event, **context: events.append((event, context)),
    )

    log_task_prerun(sender=task, task_id="task-42")
    log_task_postrun(sender=task, task_id="task-42", state="SUCCESS")

    assert [event for event, _ in events] == ["celery.task.started", "celery.task.finished"]
    assert all(context["task_id"] == "task-42" for _, context in events)
    assert all(context["correlation_id"] == expected_correlation_id for _, context in events)
