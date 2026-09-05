import random
from typing import NoReturn

from celery.exceptions import OperationalError as BrokerOperationalError
from celery.exceptions import Reject


def make_delivery_token(*, task_id: str | None, retries: int) -> str:
    return f"{task_id or 'direct'}:{retries}"


def _backoff(*, retries: int, floor: int) -> int:
    base = min(300, max(floor, 2 ** min(retries + 1, 8)))
    return min(300, max(1, int(base + random.uniform(0, base * 0.25))))


def provider_backoff(*, retries: int, retry_after_seconds: int | None = None) -> int:
    return _backoff(retries=retries, floor=retry_after_seconds or 1)


def database_backoff(*, retries: int) -> int:
    return _backoff(retries=retries, floor=2)


def retry_or_requeue(task, *, exc: Exception, countdown: int) -> NoReturn:
    try:
        raise task.retry(exc=exc, countdown=countdown)
    except BrokerOperationalError as error:
        raise Reject(error, requeue=True) from error
