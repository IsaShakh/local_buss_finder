from config.celery import app


def test_pipeline_tasks_are_routed_to_separate_queues():
    routes = app.conf.task_routes

    assert routes is not None
    assert routes["apps.discovery.tasks.*"]["queue"] == "discovery"
    assert routes["apps.normalization.tasks.*"]["queue"] == "normalization"
    assert app.conf.task_serializer == "json"
    assert app.conf.accept_content == ["json"]
    assert app.conf.task_track_started is True
    assert app.conf.task_acks_late is True
    assert app.conf.task_reject_on_worker_lost is True
    assert app.conf.task_publish_retry is True
    assert app.conf.task_publish_retry_policy["max_retries"] == 3


def test_celery_uses_redis_only_as_broker():
    assert app.conf.broker_url == "redis://redis:6379/0"
    assert app.conf.task_ignore_result is True
    assert app.conf.result_backend is None
