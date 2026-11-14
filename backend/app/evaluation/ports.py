"""What the Evaluation Run task answers and judges through: the model gateway, the Guardrail
pipeline, the local embedders retrieval embeds questions with, the judge's timeout and the
clock.

The API installs them at startup and the worker at its start; the task reads them with
``current_evaluation_ports``. In tests the task runs eagerly in the API's process, and the
API's ports hand it the API's own gateway and Guardrails, so tests script models and fakes
through ``app.state`` as they do for the Playground.
"""

from collections.abc import Callable
from dataclasses import dataclass

import httpx2

from app.core.clock import Clock
from app.embeddings.port import Embedder
from app.gateway.gateway import ModelGateway
from app.guardrails.pipeline import GuardrailPipeline


@dataclass
class EvaluationPorts:
    # Builds the model gateway on an HTTP client the task opens on its own event loop.
    open_gateway: Callable[[httpx2.AsyncClient], ModelGateway]
    guardrails: GuardrailPipeline
    embedders: dict[str, Embedder]
    judge_timeout_s: float
    # The clock answers and the Run's end are timed by.
    clock: Callable[[], Clock]


class EvaluationPortsNotInstalledError(RuntimeError):
    """An Evaluation Run task ran before the API or worker installed its ports."""


_installed: list[EvaluationPorts] = []


def install_evaluation_ports(ports: EvaluationPorts) -> None:
    _installed[:] = [ports]


def current_evaluation_ports() -> EvaluationPorts:
    if not _installed:
        raise EvaluationPortsNotInstalledError("The evaluation ports haven't been installed")
    return _installed[0]
