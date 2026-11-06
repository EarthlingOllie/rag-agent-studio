"""The Celery application shared by the API (to enqueue), the worker and Beat."""

from celery import Celery

from app.core.settings import Settings

HEALTH_CHECK_TASK = "worker.health_check"

celery_app = Celery(
    "rag_agent_studio",
    include=[
        "app.worker.tasks",
        "app.documents.tasks",
        "app.projects.tasks",
        "app.re_embedding.tasks",
    ],
)


def configure_celery(settings: Settings) -> Celery:
    redis_url = str(settings.redis_url)
    celery_app.conf.update(
        broker_url=redis_url,
        result_backend=redis_url,
        result_expires=300,
        task_always_eager=settings.celery_task_always_eager,
        task_eager_propagates=True,
        broker_connection_retry_on_startup=True,
        beat_schedule={
            "worker-health-check": {"task": HEALTH_CHECK_TASK, "schedule": 300.0},
        },
    )
    return celery_app
