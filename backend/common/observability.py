import json
import logging
import re
from datetime import date, datetime
from typing import Literal
from uuid import UUID, uuid4

from pythonjsonlogger.json import JsonFormatter

logger = logging.getLogger(__name__)

STRUCTURED_FIELDS = (
    "timestamp",
    "level",
    "service",
    "event",
    "message",
    "request_id",
    "task_id",
    "correlation_id",
    "campaign_id",
    "source_run_id",
    "source",
    "source_record_id",
    "error_code",
    "duration_ms",
)
_STRUCTURED_FIELD_SET = frozenset(STRUCTURED_FIELDS)
_RESOLUTION_FIELD_SET = _STRUCTURED_FIELD_SET | {
    "owner_id",
    "normalized_record_id",
    "business_id",
    "candidate_ids",
    "resolution_version",
    "score",
    "action",
    "signal_codes",
}
_CORRELATION_ID_PATTERN = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z", re.ASCII)


class StructuredJsonFormatter(JsonFormatter):
    def process_log_record(self, log_data: dict) -> dict:
        message = log_data.get("message")
        if isinstance(message, str):
            try:
                structured = json.loads(message)
            except json.JSONDecodeError:
                pass
            else:
                if isinstance(structured, dict) and set(structured) == _STRUCTURED_FIELD_SET:
                    return structured
                if (
                    isinstance(structured, dict)
                    and set(structured) == _RESOLUTION_FIELD_SET
                    and structured.get("event")
                    in {
                        "business.resolution.seeded",
                        "business.resolution.source_identity",
                        "business.resolution.automatic",
                    }
                ):
                    return structured
        return super().process_log_record(log_data)


def _safe_scalar(value: object) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError("structured log context values must be scalar")


def sanitize_log_context(context: dict[str, object]) -> dict[str, str | int | float | bool | None]:
    safe: dict[str, str | int | float | bool | None] = {}
    for key, value in context.items():
        if key not in _STRUCTURED_FIELD_SET:
            continue
        try:
            safe[key] = _safe_scalar(value)
        except TypeError:
            continue
    return safe


def structured_event(event: str, **context: object) -> None:
    _emit_structured_event(event, sanitize_log_context(context))


def structured_resolution_event(
    *,
    owner_id: UUID | int,
    normalized_record_id: UUID,
    business_id: UUID,
    candidate_ids: tuple[UUID, ...],
    resolution_version: str,
    score: int,
    action: Literal["seeded", "source_identity", "automatic"],
    signal_codes: tuple[str, ...],
    campaign_id: UUID,
    source_run_id: UUID | None,
    source_record_id: UUID,
    source: str,
) -> None:
    """Resolution audit schema accepts identifiers and codes, never signal values."""
    _emit_structured_event(
        f"business.resolution.{action}",
        {
            "owner_id": _safe_scalar(owner_id),
            "normalized_record_id": str(normalized_record_id),
            "business_id": str(business_id),
            "candidate_ids": [str(pk) for pk in candidate_ids],
            "resolution_version": resolution_version,
            "score": score,
            "action": action,
            "signal_codes": list(signal_codes),
            "campaign_id": str(campaign_id),
            "source_run_id": str(source_run_id) if source_run_id else None,
            "source_record_id": str(source_record_id),
            "source": source,
            "correlation_id": str(campaign_id),
            "message": "Normalized source record resolved",
        },
    )


def _emit_structured_event(event: str, safe: dict[str, object]) -> None:
    level = str(safe.get("level") or "info").lower()
    payload: dict[str, object] = dict.fromkeys(STRUCTURED_FIELDS)
    payload.update(
        {
            "timestamp": datetime.now().astimezone().isoformat(),
            "level": level,
            "service": "backend",
            "event": event,
            "message": safe.get("message") or event,
        }
    )
    payload.update(
        {
            key: value
            for key, value in safe.items()
            if key not in {"timestamp", "level", "service", "event"}
        }
    )
    log = getattr(logger, level, logger.info)
    log(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def safe_correlation_id(value: object, *, fallback: str | None = None) -> str:
    if isinstance(value, str) and _CORRELATION_ID_PATTERN.fullmatch(value):
        return value
    if fallback is not None and _CORRELATION_ID_PATTERN.fullmatch(fallback):
        return fallback
    return str(uuid4())
