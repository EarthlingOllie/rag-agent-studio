"""The production adapters: real provider clients, sharing one ``httpx2`` client.

- Anthropic chat and OpenAI chat and embeddings use Pydantic AI's own models and providers.
- Voyage has no Pydantic AI provider without its SDK, so its embedder and reranker are thin
  HTTP clients here.
- Bedrock embedders call Bedrock Runtime's ``InvokeModel`` through boto3, signed with the
  credential's access keys or with a session of the Owner's role, assumed through STS and
  cached the way credential checks cache them (``AssumedRoleSessions``). Bedrock chat and
  rerank clients are not built yet.
"""

import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial
from typing import Any

import httpx2
from botocore.exceptions import ClientError
from pydantic_ai.embeddings import EmbeddingModel, EmbeddingResult, EmbeddingSettings
from pydantic_ai.embeddings.openai import OpenAIEmbeddingModel
from pydantic_ai.embeddings.result import EmbedInputType
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import RequestUsage

from app.credentials.bedrock_verifier import AssumedRoleSessions, AwsKeys, ClientFactory
from app.credentials.registry import Provider
from app.embeddings.registry import embedding_model
from app.gateway.gateway import UnsupportedCredentialError
from app.gateway.ports import BedrockAccount, RankedDocument, Reranker

VOYAGE_API = "https://api.voyageai.com/v1"


def _unsupported(provider: Provider) -> UnsupportedCredentialError:
    return UnsupportedCredentialError(
        f"Bedrock chat and rerank models are not available yet ({provider} clients for them "
        "are not built)."
    )


async def _voyage_post(
    client: httpx2.AsyncClient, secret: str, path: str, model: str, body: dict[str, Any]
) -> dict[str, Any]:
    response = await client.post(
        f"{VOYAGE_API}/{path}",
        headers={"Authorization": f"Bearer {secret}"},
        json=body | {"model": model},
    )
    if response.status_code >= 400:
        raise ModelHTTPError(response.status_code, model, response.json())
    answer: dict[str, Any] = response.json()
    return answer


class VoyageEmbeddingModel(EmbeddingModel):
    def __init__(self, client: httpx2.AsyncClient, secret: str, model: str) -> None:
        super().__init__()
        self._client = client
        self._secret = secret
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def system(self) -> str:
        return "voyage"

    async def embed(
        self,
        inputs: str | Sequence[str],
        *,
        input_type: EmbedInputType,
        settings: EmbeddingSettings | None = None,
    ) -> EmbeddingResult:
        texts, _ = self.prepare_embed(inputs, settings)
        answer = await _voyage_post(
            self._client,
            self._secret,
            "embeddings",
            self._model,
            {"input": texts, "input_type": input_type},
        )
        ordered = sorted(answer["data"], key=lambda item: item["index"])
        return EmbeddingResult(
            [item["embedding"] for item in ordered],
            inputs=texts,
            input_type=input_type,
            model_name=self._model,
            provider_name=self.system,
            usage=RequestUsage(input_tokens=answer["usage"]["total_tokens"]),
        )


class VoyageReranker:
    def __init__(self, client: httpx2.AsyncClient, secret: str, model: str) -> None:
        self._client = client
        self._secret = secret
        self.model_name = model

    async def rerank(
        self, query: str, documents: Sequence[str], *, top_k: int | None = None
    ) -> list[RankedDocument]:
        body: dict[str, Any] = {"query": query, "documents": list(documents)}
        if top_k is not None:
            body["top_k"] = top_k
        answer = await _voyage_post(self._client, self._secret, "rerank", self.model_name, body)
        return [RankedDocument(item["index"], item["relevance_score"]) for item in answer["data"]]


# Cohere Embed on Bedrock takes at most 96 texts per call; Titan takes one.
COHERE_BATCH = 96
_COHERE_INPUT_TYPES = {"document": "search_document", "query": "search_query"}


@dataclass(frozen=True)
class BedrockClients:
    """How Bedrock is reached: the platform's cache of assumed-role sessions, and the factory
    that builds boto3 clients signed with given keys."""

    sessions: AssumedRoleSessions
    clients: ClientFactory


def _http_error(error: ClientError, model: str) -> ModelHTTPError:
    status = int(error.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 500))
    return ModelHTTPError(status, model, dict(error.response.get("Error", {})))


class BedrockEmbeddingModel(EmbeddingModel):
    """Titan Text Embeddings V2 (one text per call) and Cohere Embed (batches) on Bedrock.

    boto3 is synchronous, so each ``embed`` runs in a worker thread."""

    def __init__(self, bedrock: BedrockClients, account: BedrockAccount, model: str) -> None:
        super().__init__()
        self._bedrock = bedrock
        self._account = account
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def system(self) -> str:
        return "bedrock"

    async def embed(
        self,
        inputs: str | Sequence[str],
        *,
        input_type: EmbedInputType,
        settings: EmbeddingSettings | None = None,
    ) -> EmbeddingResult:
        texts, _ = self.prepare_embed(inputs, settings)
        try:
            vectors, tokens = await asyncio.to_thread(self._embed, texts, input_type)
        except ClientError as error:
            raise _http_error(error, self._model) from error
        return EmbeddingResult(
            vectors,
            inputs=texts,
            input_type=input_type,
            model_name=self._model,
            provider_name=self.system,
            usage=RequestUsage(input_tokens=tokens),
        )

    def _keys(self) -> AwsKeys:
        account = self._account
        if account.role_arn is not None:
            return self._bedrock.sessions.keys_for(account.role_arn, str(account.external_id))
        return AwsKeys(str(account.access_key_id), str(account.secret_access_key))

    def _embed(self, texts: list[str], input_type: EmbedInputType) -> tuple[list[list[float]], int]:
        runtime = self._bedrock.clients("bedrock-runtime", self._account.region, self._keys())
        invoke = partial(self._invoke, runtime)
        if self._model.startswith("cohere."):
            vectors: list[list[float]] = []
            for start in range(0, len(texts), COHERE_BATCH):
                body = {
                    "texts": texts[start : start + COHERE_BATCH],
                    "input_type": _COHERE_INPUT_TYPES[input_type],
                    "truncate": "END",
                }
                vectors.extend(invoke(body)["embeddings"])
            # Cohere's answer doesn't count tokens.
            return vectors, 0
        dimension = embedding_model(self._model).dimension
        answers = [
            invoke({"inputText": text, "dimensions": dimension, "normalize": True})
            for text in texts
        ]
        tokens = sum(answer["inputTextTokenCount"] for answer in answers)
        return [answer["embedding"] for answer in answers], tokens

    def _invoke(self, runtime: Any, body: dict[str, Any]) -> dict[str, Any]:
        response = runtime.invoke_model(
            modelId=self._model,
            body=json.dumps(body).encode(),
            contentType="application/json",
            accept="application/json",
        )
        answer: dict[str, Any] = json.loads(response["body"].read())
        return answer


class LiveModelAdapters:
    def __init__(self, client: httpx2.AsyncClient, bedrock: BedrockClients) -> None:
        self._client = client
        self.bedrock = bedrock

    def chat(self, provider: Provider, secret: str, model: str) -> Model:
        if provider is Provider.ANTHROPIC:
            return AnthropicModel(
                model, provider=AnthropicProvider(api_key=secret, http_client=self._client)
            )
        if provider is Provider.OPENAI:
            return OpenAIChatModel(model, provider=self._openai(secret))
        raise _unsupported(provider)

    def embedder(self, provider: Provider, secret: str, model: str) -> EmbeddingModel:
        if provider is Provider.OPENAI:
            return OpenAIEmbeddingModel(model, provider=self._openai(secret))
        # The gateway has checked the provider offers embeddings: the API-key ones are OpenAI
        # and Voyage, and Bedrock goes through ``bedrock_embedder``.
        return VoyageEmbeddingModel(self._client, secret, model)

    def bedrock_embedder(self, account: BedrockAccount, model: str) -> EmbeddingModel:
        return BedrockEmbeddingModel(self.bedrock, account, model)

    def reranker(self, provider: Provider, secret: str, model: str) -> Reranker:
        if provider is Provider.VOYAGE:
            return VoyageReranker(self._client, secret, model)
        raise _unsupported(provider)

    def _openai(self, secret: str) -> OpenAIProvider:
        return OpenAIProvider(api_key=secret, http_client=self._client)
