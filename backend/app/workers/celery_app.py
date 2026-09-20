import sys

from celery import Celery

from app.core.config import get_settings


settings = get_settings()
celery_app = Celery(
    "opspilot",
    broker=settings.redis_url,
    backend=settings.effective_celery_result_backend,
    include=[
        "app.workers.tasks.event_tasks",
        "app.workers.tasks.investigation_tasks",
        "app.workers.tasks.rag_tasks",
        "app.workers.tasks.gateway_tasks",
    ],
)

# Windows does not support the prefork pool (billiard semaphores fail with
# PermissionError / WinError 5).  Use 'solo' for local dev; Linux/Docker
# containers keep the default prefork behaviour.
_worker_pool = "solo" if sys.platform == "win32" else "prefork"

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    enable_utc=True,
    timezone="UTC",
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_pool=_worker_pool,
    worker_prefetch_multiplier=settings.celery_worker_prefetch_multiplier,
    worker_concurrency=settings.celery_worker_concurrency,
    task_soft_time_limit=settings.celery_task_soft_time_limit,
    task_time_limit=settings.celery_task_time_limit,
    task_default_queue="opspilot",
    broker_connection_retry_on_startup=True,
)
celery_app.autodiscover_tasks(["app.workers"])

from app.workers.tasks import event_tasks, gateway_tasks, investigation_tasks, rag_tasks  # noqa: E402,F401
