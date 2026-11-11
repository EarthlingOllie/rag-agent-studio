"""The capability registry: each provider, how it authenticates, what it can do and with which
models. Maintained in code, alongside the price table (ticket 02-04); pickers read it through
``GET /api/providers``.
"""

import enum
from collections.abc import Sequence
from dataclasses import dataclass


class Provider(enum.StrEnum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    BEDROCK = "bedrock"
    VOYAGE = "voyage"
    # The demo provider: canned answers from the Knowledge Base, no AI and no key
    # (``app.gateway.demo``). The seeded demo Organisation uses it.
    DEMO = "demo"


class AuthKind(enum.StrEnum):
    API_KEY = "api_key"
    AWS_ROLE = "aws_role"
    AWS_ACCESS_KEYS = "aws_access_keys"


class Capability(enum.StrEnum):
    CHAT = "chat"
    EMBEDDINGS = "embeddings"
    RERANK = "rerank"


@dataclass(frozen=True)
class Model:
    id: str
    name: str
    # Whether the model can call tools, which Agentic Retrieval Mode's Knowledge Search needs.
    # A property of the model, not a Capability: only chat models call tools.
    supports_tools: bool = False


def chat(id: str, name: str, *, supports_tools: bool = True) -> Model:
    """A chat model; most support tools."""
    return Model(id, name, supports_tools)


@dataclass(frozen=True)
class ProviderSpec:
    provider: Provider
    name: str
    auth_kinds: tuple[AuthKind, ...]
    models: dict[Capability, tuple[Model, ...]]

    @property
    def capabilities(self) -> tuple[Capability, ...]:
        return tuple(self.models)


PROVIDERS: dict[Provider, ProviderSpec] = {
    spec.provider: spec
    for spec in (
        ProviderSpec(
            Provider.ANTHROPIC,
            "Anthropic",
            (AuthKind.API_KEY,),
            {
                Capability.CHAT: (
                    chat("claude-opus-4-1", "Claude Opus 4.1"),
                    chat("claude-sonnet-4-5", "Claude Sonnet 4.5"),
                    chat("claude-haiku-4-5", "Claude Haiku 4.5"),
                ),
            },
        ),
        ProviderSpec(
            Provider.OPENAI,
            "OpenAI",
            (AuthKind.API_KEY,),
            {
                Capability.CHAT: (
                    chat("gpt-4.1", "GPT-4.1"),
                    chat("gpt-4.1-mini", "GPT-4.1 mini"),
                    chat("gpt-4o-mini", "GPT-4o mini"),
                ),
                Capability.EMBEDDINGS: (
                    Model("text-embedding-3-small", "text-embedding-3-small"),
                    Model("text-embedding-3-large", "text-embedding-3-large"),
                ),
            },
        ),
        ProviderSpec(
            Provider.BEDROCK,
            "Amazon Bedrock",
            (AuthKind.AWS_ROLE, AuthKind.AWS_ACCESS_KEYS),
            {
                Capability.CHAT: (
                    chat("anthropic.claude-sonnet-4-5-20250929-v1:0", "Claude Sonnet 4.5"),
                    chat("anthropic.claude-haiku-4-5-20251001-v1:0", "Claude Haiku 4.5"),
                    chat("amazon.nova-pro-v1:0", "Amazon Nova Pro"),
                    # Bedrock's Converse API gives Mistral 7B Instruct no tool use.
                    chat(
                        "mistral.mistral-7b-instruct-v0:2",
                        "Mistral 7B Instruct",
                        supports_tools=False,
                    ),
                ),
                Capability.EMBEDDINGS: (
                    Model("amazon.titan-embed-text-v2:0", "Titan Text Embeddings V2"),
                    Model("cohere.embed-multilingual-v3", "Cohere Embed Multilingual v3"),
                ),
                Capability.RERANK: (Model("cohere.rerank-v3-5:0", "Cohere Rerank 3.5"),),
            },
        ),
        ProviderSpec(
            Provider.VOYAGE,
            "Voyage AI",
            (AuthKind.API_KEY,),
            {
                Capability.EMBEDDINGS: (
                    Model("voyage-3.5", "voyage-3.5"),
                    Model("voyage-3.5-lite", "voyage-3.5-lite"),
                    Model("voyage-multilingual-2", "voyage-multilingual-2"),
                ),
                Capability.RERANK: (
                    Model("rerank-2.5", "rerank-2.5"),
                    Model("rerank-2.5-lite", "rerank-2.5-lite"),
                ),
            },
        ),
        ProviderSpec(
            Provider.DEMO,
            "Demo (not a real model)",
            (AuthKind.API_KEY,),
            {
                Capability.CHAT: (
                    chat("demo-chat", "Demo model"),
                    chat("demo-naive", "Naive demo model (obeys injected instructions)"),
                )
            },
        ),
    )
}


def supports_tools(provider: Provider, model: str) -> bool:
    """Whether the provider's chat model can call tools; False for a model the registry
    doesn't list (one since dropped from it)."""
    offered = PROVIDERS[provider].models.get(Capability.CHAT, ())
    return any(m.supports_tools for m in offered if m.id == model)


def models_for(
    provider: Provider, capabilities: Sequence[str], capability: Capability
) -> tuple[Model, ...]:
    """The models a credential offers for one capability: none unless it was given that
    capability, otherwise the provider's models for it."""
    if capability not in capabilities:
        return ()
    return PROVIDERS[provider].models.get(capability, ())
