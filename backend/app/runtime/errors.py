"""Provider errors: what went wrong when a model provider failed, as a typed ``ErrorEvent``
with a message an Editor can act on.

Pydantic AI's provider models raise ``ModelAPIError``s sorted into categories (an
authentication error, a rate limit, a model not found, …), each also a ``ModelHTTPError`` when
it came with an HTTP status. The gateway raises its own errors when it can't build the model.
``provider_error`` turns any of them into one of four kinds; anything else is not a provider
error and is left to propagate.
"""

import logging
from dataclasses import dataclass
from enum import StrEnum

from pydantic_ai.exceptions import (
    ModelAPIError,
    ModelAuthenticationError,
    ModelHTTPError,
    ModelNotFoundError,
    ModelQuotaExceededError,
    ModelRateLimitError,
    ModelUnavailableError,
    UnexpectedModelBehavior,
)

from app.gateway.gateway import ModelUnavailableError as ModelNotOffered
from app.gateway.gateway import UnsupportedCredentialError

logger = logging.getLogger(__name__)


class ProviderErrorKind(StrEnum):
    INVALID_KEY = "invalid_key"
    RATE_LIMITED = "rate_limited"
    MODEL_UNAVAILABLE = "model_unavailable"
    PROVIDER_ERROR = "provider_error"


MESSAGES = {
    ProviderErrorKind.INVALID_KEY: (
        "The provider rejected the API key. An Owner can check or rotate the Provider "
        "Credential in Settings, Provider Credentials."
    ),
    ProviderErrorKind.RATE_LIMITED: (
        "The provider says this key is over its rate limit or quota. Wait a moment and try "
        "again, or check the provider account's limits and billing."
    ),
    ProviderErrorKind.MODEL_UNAVAILABLE: (
        "The model {model} isn't available from the provider right now. Try again later, or "
        "choose another model for the Draft or the Default Model."
    ),
    ProviderErrorKind.PROVIDER_ERROR: (
        "The provider couldn't answer just now. Try again in a moment."
    ),
}

_BY_STATUS = {
    401: ProviderErrorKind.INVALID_KEY,
    403: ProviderErrorKind.INVALID_KEY,
    402: ProviderErrorKind.RATE_LIMITED,
    429: ProviderErrorKind.RATE_LIMITED,
    404: ProviderErrorKind.MODEL_UNAVAILABLE,
}


@dataclass(frozen=True)
class ErrorEvent:
    """The provider failed: the turn ends here, with no answer."""

    kind: ProviderErrorKind
    message: str


def _kind(error: Exception) -> ProviderErrorKind:
    if isinstance(error, ModelAuthenticationError):
        return ProviderErrorKind.INVALID_KEY
    if isinstance(error, ModelRateLimitError | ModelQuotaExceededError):
        return ProviderErrorKind.RATE_LIMITED
    if isinstance(
        error,
        ModelNotFoundError | ModelUnavailableError | ModelNotOffered | UnsupportedCredentialError,
    ):
        return ProviderErrorKind.MODEL_UNAVAILABLE
    if isinstance(error, ModelHTTPError):
        return _BY_STATUS.get(error.status_code, ProviderErrorKind.PROVIDER_ERROR)
    return ProviderErrorKind.PROVIDER_ERROR


PROVIDER_ERRORS = (
    ModelAPIError,
    UnexpectedModelBehavior,
    ModelNotOffered,
    UnsupportedCredentialError,
)


def provider_error(error: Exception, model: str) -> ErrorEvent:
    """The ``ErrorEvent`` for one of the ``PROVIDER_ERRORS``, raised while ``model`` answered
    (a provider's own error names the model it was calling). It is
    logged by kind, class and status only: a provider's error body can echo request details."""
    kind = _kind(error)
    logger.warning(
        "The model provider failed",
        extra={
            "kind": kind.value,
            "error": type(error).__name__,
            "status_code": getattr(error, "status_code", None),
        },
    )
    named = error.model_name if isinstance(error, ModelAPIError) else model
    return ErrorEvent(kind, MESSAGES[kind].format(model=named))
