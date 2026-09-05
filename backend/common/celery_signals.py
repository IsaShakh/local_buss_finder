from celery.signals import task_failure, task_postrun, task_prerun

from common.observability import safe_correlation_id, structured_event


def _correlation_id(sender, task_id: str) -> str:
    request = getattr(sender, "request", None)
    headers = getattr(request, "headers", None) or {}
    candidate = headers.get("correlation_id") or headers.get("correlation-id")
    return safe_correlation_id(candidate, fallback=task_id)


@task_prerun.connect
def log_task_prerun(*, sender=None, task_id=None, **kwargs) -> None:
    if sender is None or task_id is None:
        return
    structured_event(
        "celery.task.started",
        task_id=task_id,
        correlation_id=_correlation_id(sender, task_id),
        message="Celery task started",
    )


@task_postrun.connect
def log_task_postrun(*, sender=None, task_id=None, state=None, **kwargs) -> None:
    if sender is None or task_id is None:
        return
    structured_event(
        "celery.task.finished",
        task_id=task_id,
        correlation_id=_correlation_id(sender, task_id),
        error_code=None if state == "SUCCESS" else state,
        message="Celery task finished",
    )


@task_failure.connect
def log_task_failure(*, sender=None, task_id=None, exception=None, **kwargs) -> None:
    if sender is None or task_id is None:
        return
    structured_event(
        "celery.task.failed",
        level="error",
        task_id=task_id,
        correlation_id=_correlation_id(sender, task_id),
        error_code=None if exception is None else type(exception).__name__,
        message="Celery task failed",
    )
