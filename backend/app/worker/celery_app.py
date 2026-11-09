"""The Celery application shared by the API (to enqueue), the worker and Beat."""

from celery import Celery
from celery.schedules import crontab

from app.core.settings import Settings

HEALTH_CHECK_TASK = "worker.health_check"
CLEAR_BUDGET_ALERTS_TASK = "embed.clear_budget_alerts"
# The usage rollup (app.analytics.tasks), which Beat runs hourly.
ROLL_UP_TASK = "analytics.roll_up_usage"
# The retention purge (app.retention.tasks), which Beat runs daily.
PURGE_TASK = "retention.purge_expired"

celery_app = Celery(
    "rag_agent_studio",
    include=[
        "app.worker.tasks",
        "app.analytics.tasks",
        "app.documents.tasks",
        "app.projects.tasks",
        "app.re_embedding.tasks",
        "app.embed.tasks",
        "app.retention.tasks",
    ],
)
# Schedules are in UTC: the Token Budget's day is the UTC date.
celery_app.conf.update(timezone="UTC", enable_utc=True)


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
            # A new UTC date starts a new Token Budget; its alert flags go too.
            "clear-token-budget-alerts": {
                "task": CLEAR_BUDGET_ALERTS_TASK,
                "schedule": crontab(minute="0", hour="0"),
            },
            # Hourly, a few minutes past the hour: the current day's usage rollups, and the
            # previous day's finalised once it is over.
            "usage-rollup": {"task": ROLL_UP_TASK, "schedule": crontab(minute=5)},
            # Daily, after the 00:05 rollup has finalised the previous day: Message text and
            # feedback comments older than each Retention Window.
            "retention-purge": {
                "task": PURGE_TASK,
                "schedule": crontab(minute="35", hour="0"),
            },
        },
    )
    return celery_app
