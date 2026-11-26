"""The Celery application shared by the API (to send jobs, through the Job publisher), the worker
and Beat."""

from celery import Celery
from celery.schedules import crontab

from app.core.settings import Settings

HEALTH_CHECK_TASK = "worker.health_check"
# The jobs the application queues, through the Job publisher (app.worker.publisher).
INGEST_TASK = "documents.ingest"
DELETE_OBJECTS_TASK = "documents.delete_objects"
EVALUATION_RUN_TASK = "evaluation.run"
LIVE_VERDICT_TASK = "evaluation.live_verdict"
SUGGESTION_RUN_TASK = "suggestions.run"
RE_EMBED_TASK = "projects.re_embed"
DELETE_PROJECT_TASK = "projects.delete"
CLEAR_BUDGET_ALERTS_TASK = "embed.clear_budget_alerts"
# The usage rollup (app.analytics.tasks), which Beat runs hourly.
ROLL_UP_TASK = "analytics.roll_up_usage"
# The retention purge (app.retention.tasks), which Beat runs hourly.
PURGE_TASK = "retention.purge_expired"
# The job sweeper (app.jobs.tasks, ADR-0020), which Beat runs every minute and each worker sends
# once as it starts.
SWEEP_TASK = "jobs.sweep"

celery_app = Celery(
    "rag_agent_studio",
    include=[
        "app.worker.tasks",
        "app.analytics.tasks",
        "app.documents.tasks",
        "app.evaluation.tasks",
        "app.projects.tasks",
        "app.re_embedding.tasks",
        "app.embed.tasks",
        "app.retention.tasks",
        "app.suggestions.tasks",
        "app.jobs.tasks",
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
        # A worker takes one message at a time and acknowledges it once the task has run, so a
        # message waiting behind a long job can go to another worker. A message whose worker was
        # lost is not put back on the queue: the sweeper restarts the job, with a cap (ADR-0020).
        worker_prefetch_multiplier=1,
        task_acks_late=True,
        task_reject_on_worker_lost=False,
        beat_schedule={
            "worker-health-check": {"task": HEALTH_CHECK_TASK, "schedule": 300.0},
            # A new UTC date starts a new Token Budget; its alert flags go too. Hourly, so the
            # run after a midnight Beat missed still resets the day that ended.
            "clear-token-budget-alerts": {
                "task": CLEAR_BUDGET_ALERTS_TASK,
                "schedule": crontab(minute="0"),
            },
            # Hourly, a few minutes past the hour: the current day's usage rollups, and the
            # previous day's finalised once it is over.
            "usage-rollup": {"task": ROLL_UP_TASK, "schedule": crontab(minute=5)},
            # Hourly, half an hour after each rollup (the 00:05 one finalises the previous
            # day): Message text and feedback comments older than each Retention Window. A
            # missed run leaves text at most an hour past its window.
            "retention-purge": {"task": PURGE_TASK, "schedule": crontab(minute="35")},
            # Every minute: send again jobs queued too long, and deal with jobs whose heartbeat
            # stopped (ADR-0020).
            "job-sweeper": {"task": SWEEP_TASK, "schedule": 60.0},
        },
    )
    return celery_app
