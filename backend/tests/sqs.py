"""The test run's SQS queues on Floci, for the few tests that send through the real broker or
start a real worker. Each xdist worker has its own pair (``tests.conftest.TEST_QUEUES``)."""

import base64
import json
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.core.settings import load_settings
from app.worker.queues import create_queues, sqs_client
from tests.conftest import TEST_SQS_ENDPOINT_URL

if TYPE_CHECKING:
    from mypy_boto3_sqs import SQSClient


def client() -> "SQSClient":
    return sqs_client(load_settings())


def queue_url(name: str) -> str:
    return f"{TEST_SQS_ENDPOINT_URL}/000000000000/{name}"


def empty_queues(names: Iterable[str] | None = None) -> None:
    """The queues (by default the two the settings name) exist and hold nothing.

    A worker stopped while it waits for a message (SQS long polling) can leave that wait open on
    Floci for a few seconds, and the next message sent would go to it and stay hidden for the
    queue's visibility timeout. So a few throwaway messages go first, to answer any such wait,
    and the purge then removes them, taken or not."""
    settings = load_settings()
    create_queues(settings)
    sqs = client()
    urls = [
        queue_url(name)
        for name in (names or (settings.general_queue_name, settings.runs_queue_name))
    ]
    for url in urls:
        for _ in range(_THROWAWAY_MESSAGES):
            sqs.send_message(QueueUrl=url, MessageBody="throwaway")
    time.sleep(0.2)
    for url in urls:
        sqs.purge_queue(QueueUrl=url)


_THROWAWAY_MESSAGES = 3


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
    settings = load_settings()
    sqs = client()
    url = str(settings.general_queue_url if queue == "general" else settings.runs_queue_url)
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
