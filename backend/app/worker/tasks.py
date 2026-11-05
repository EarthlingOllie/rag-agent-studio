from app.worker.celery_app import HEALTH_CHECK_TASK, celery_app


@celery_app.task(name=HEALTH_CHECK_TASK)
def health_check() -> str:
    """Answers the API's worker health probe; Beat also runs it on a schedule."""
    return "pong"
