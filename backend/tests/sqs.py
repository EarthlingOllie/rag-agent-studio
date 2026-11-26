"""The test run's SQS queues on Floci, for the few tests that send through the real broker or
start a real worker. Each xdist worker has its own pair (``tests.conftest.TEST_QUEUES``)."""

import base64
import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.core.settings import load_settings
from app.worker.queues import create_queues, sqs_client
from tests.conftest import TEST_QUEUE_URLS, TEST_QUEUES

if TYPE_CHECKING:
    from mypy_boto3_sqs import SQSClient


def client() -> "SQSClient":
    return sqs_client(load_settings())


def empty_queues(names: Iterable[str] = TEST_QUEUES.values()) -> None:
    """The queues (by default the test run's two) exist and hold nothing. Needs the test
    environment (``settings_env``)."""
    create_queues(load_settings())
    sqs = client()
    for name in names:
        sqs.purge_queue(QueueUrl=sqs.get_queue_url(QueueName=name)["QueueUrl"])


@dataclass(frozen=True)
class Message:
    """A Celery message as it sits in SQS: its headers and the task's arguments."""

    headers: dict[str, Any]
    args: list[Any]
    kwargs: dict[str, Any]
    raw: str

    @property
    def task(self) -> str:
        task: str = self.headers["task"]
        return task


def take_messages(queue: str) -> list[Message]:
    """Receives (and deletes) every message waiting on the ``general`` or ``runs`` queue."""
    sqs = client()
    url = TEST_QUEUE_URLS[queue]
    messages: list[Message] = []
    while True:
        received = sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=10, WaitTimeSeconds=1)
        batch = received.get("Messages", [])
        if not batch:
            return messages
        for message in batch:
            messages.append(_decode(message["Body"]))
            sqs.delete_message(QueueUrl=url, ReceiptHandle=message["ReceiptHandle"])


def _decode(body: str) -> Message:
    # Kombu base64-encodes the envelope; Celery's body inside it is base64 JSON too.
    envelope = json.loads(base64.b64decode(body))
    args, kwargs, _embed = json.loads(base64.b64decode(envelope["body"]))
    return Message(headers=envelope["headers"], args=args, kwargs=kwargs, raw=body)
