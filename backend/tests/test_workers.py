import pytest

from app.core.config import Settings
from app.workers.celery_app import celery_app
from app.workers.tasks.event_tasks import process_event_task


def test_celery_uses_json_and_registers_only_application_task() -> None:
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.result_serializer == "json"
    assert celery_app.conf.accept_content == ["json"]
    assert "opspilot.process_event" in celery_app.tasks
    assert process_event_task.name == "opspilot.process_event"


def test_celery_settings_are_environment_driven() -> None:
    settings = Settings(redis_url="redis://example:6379/4", celery_result_backend=None)
    assert settings.effective_celery_result_backend == "redis://example:6379/4"
    assert settings.celery_task_max_retries == 3


def test_task_rejects_untrusted_or_malformed_event_identifiers() -> None:
    empty = process_event_task.apply(args=[""])
    arbitrary = process_event_task.apply(args=[{"event_id": "not-a-safe-task-payload"}])
    assert empty.failed and isinstance(empty.result, ValueError)
    assert arbitrary.failed and isinstance(arbitrary.result, ValueError)
