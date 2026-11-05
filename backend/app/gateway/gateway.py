"""The single model factory. Every model call in the platform starts here.

``ModelGateway`` turns a Provider Credential and a model name into a Pydantic AI chat model,
an embedder or a reranker. It refuses a model the credential doesn't offer for that
capability, opens the credential's sealed secret, and hands both to its adapters. Tests and
``docker compose`` plug in the fake adapters here, and only here.
"""

from pydantic_ai.embeddings import EmbeddingModel
from pydantic_ai.models import Model

from app.credentials.models import ProviderCredential
from app.credentials.registry import PROVIDERS, Capability, Provider, models_for
from app.credentials.service import open_secret
from app.crypto.envelope import EnvelopeEncryption
from app.gateway.ports import ModelAdapters, Reranker


class ModelUnavailableError(Exception):
    """The credential doesn't offer this model for this capability."""


class CapabilityNotGrantedError(ModelUnavailableError):
    """The credential wasn't given the capability at all."""


class ModelNotOfferedError(ModelUnavailableError):
    """The provider doesn't offer the model for the capability."""


class UnsupportedCredentialError(Exception):
    """The adapters can't build a client for this kind of credential."""


def check_offered(credential: ProviderCredential, capability: Capability, model: str) -> None:
    """Raises ``ModelUnavailableError`` unless the credential offers ``model`` for
    ``capability``."""
    provider = Provider(credential.provider)
    if capability not in credential.capabilities:
        raise CapabilityNotGrantedError(f"This credential can't be used for {capability}.")
    if model not in {m.id for m in models_for(provider, credential.capabilities, capability)}:
        name = PROVIDERS[provider].name
        raise ModelNotOfferedError(f"{name} doesn't offer {model} for {capability}.")


class ModelGateway:
    def __init__(self, envelope: EnvelopeEncryption, adapters: ModelAdapters) -> None:
        self._envelope = envelope
        self.adapters = adapters

    def _secret(
        self, credential: ProviderCredential, capability: Capability, model: str
    ) -> tuple[Provider, str]:
        check_offered(credential, capability, model)
        if credential.secret_sealed is None:
            # A Bedrock IAM-role credential stores no secret; its clients assume the role.
            raise UnsupportedCredentialError(
                "Bedrock IAM-role credentials can't make model calls yet."
            )
        return Provider(credential.provider), open_secret(self._envelope, credential)

    def chat_model(self, credential: ProviderCredential, model: str) -> Model:
        provider, secret = self._secret(credential, Capability.CHAT, model)
        return self.adapters.chat(provider, secret, model)

    def embedder(self, credential: ProviderCredential, model: str) -> EmbeddingModel:
        provider, secret = self._secret(credential, Capability.EMBEDDINGS, model)
        return self.adapters.embedder(provider, secret, model)

    def reranker(self, credential: ProviderCredential, model: str) -> Reranker:
        provider, secret = self._secret(credential, Capability.RERANK, model)
        return self.adapters.reranker(provider, secret, model)
