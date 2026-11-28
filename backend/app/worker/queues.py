"""The job queues' SQS client, and creating the queues where nothing else does.

Terraform creates the queues in AWS. Floci (``docker compose``) starts empty, so there the API
creates both at startup when SQS_CREATE_QUEUES says so, as it does the bucket. They get the
visibility timeouts the queue module gives them in AWS.
"""

from typing import TYPE_CHECKING

import boto3

from app.core.settings import Settings
from app.worker.celery_app import QueueKind

if TYPE_CHECKING:
    from mypy_boto3_sqs import SQSClient

# How long a received message stays hidden from other workers, in seconds: one hour on the
# general queue, twelve (the SQS maximum) on the runs queue (infra/modules/queue).
VISIBILITY_TIMEOUT_SECONDS: dict[QueueKind, int] = {"general": 60 * 60, "runs": 12 * 60 * 60}


def sqs_client(settings: Settings) -> "SQSClient":
    secret = settings.sqs_secret_access_key
    return boto3.client(
        "sqs",
        endpoint_url=str(settings.sqs_endpoint_url) if settings.sqs_endpoint_url else None,
        region_name=settings.aws_region,
        aws_access_key_id=settings.sqs_access_key_id,
        aws_secret_access_key=secret.get_secret_value() if secret else None,
    )


def create_queues(settings: Settings) -> None:
    """Creates the general and runs queues if they don't exist yet: SQS creates a queue only
    once, and answers with the existing one when it has the same attributes."""
    client = sqs_client(settings)
    names: dict[QueueKind, str] = {
        "general": settings.general_queue_name,
        "runs": settings.runs_queue_name,
    }
    for kind, name in names.items():
        client.create_queue(
            QueueName=name,
            Attributes={"VisibilityTimeout": str(VISIBILITY_TIMEOUT_SECONDS[kind])},
        )
