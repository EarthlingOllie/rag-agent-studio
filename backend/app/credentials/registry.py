"""The capability registry: each provider, how it authenticates, what it can do and with which
models. Maintained in code, alongside the price table (ticket 02-04); pickers read it through
``GET /api/providers``.
"""

import enum
from dataclasses import dataclass


class Provider(enum.StrEnum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    BEDROCK = "bedrock"
    VOYAGE = "voyage"


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
                    Model("claude-opus-4-1", "Claude Opus 4.1"),
                    Model("claude-sonnet-4-5", "Claude Sonnet 4.5"),
                    Model("claude-haiku-4-5", "Claude Haiku 4.5"),
                ),
            },
        ),
        ProviderSpec(
            Provider.OPENAI,
            "OpenAI",
            (AuthKind.API_KEY,),
            {
                Capability.CHAT: (
                    Model("gpt-4.1", "GPT-4.1"),
                    Model("gpt-4.1-mini", "GPT-4.1 mini"),
                    Model("gpt-4o-mini", "GPT-4o mini"),
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
                    Model("anthropic.claude-sonnet-4-5-20250929-v1:0", "Claude Sonnet 4.5"),
                    Model("anthropic.claude-haiku-4-5-20251001-v1:0", "Claude Haiku 4.5"),
                    Model("amazon.nova-pro-v1:0", "Amazon Nova Pro"),
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
    )
}
