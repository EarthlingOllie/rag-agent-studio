"""Bedrock Embedding Models through the model gateway, with stubbed AWS clients.

No AWS account is used and nothing is paid for: the STS and Bedrock Runtime clients are real
boto3 clients wrapped in botocore's ``Stubber``, which checks each request against the
service's API model and answers with the recorded response shape a test queues.
"""

import base64
import io
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import httpx2
import pytest
from botocore.config import Config
from botocore.response import StreamingBody
from botocore.stub import Stubber
from pydantic_ai.exceptions import ModelHTTPError

from app.core.settings import Settings
from app.credentials.bedrock_verifier import AssumedRoleSessions, AwsKeys
from app.credentials.models import ProviderCredential
from app.credentials.registry import Capability, Provider
from app.credentials.service import seal_secret
from app.crypto.envelope import EnvelopeEncryption
from app.crypto.local_key_wrapper import LocalKeyWrapper
from app.gateway.adapters import build_model_gateway
from app.gateway.fakes import FakeModelAdapters
from app.gateway.gateway import ModelGateway, UnsupportedCredentialError
from app.gateway.live import BedrockClients, LiveModelAdapters
from tests.fakes.clock import ControllableClock

ENVELOPE = EnvelopeEncryption(LocalKeyWrapper(base64.b64encode(b"B" * 32).decode()))
REGION = "eu-west-2"
ROLE_ARN = "arn:aws:iam::111122223333:role/StudioBedrockAccess"
EXTERNAL_ID = "k2Jd8wQm4Zr7Vt1Xy9Pb3Lc6Ns0Hf5Ga"
ACCESS_KEY_ID = "AKIATESTKEYS0000WXYZ"
SECRET_ACCESS_KEY = "test-only-secret-access-key"
TITAN = "amazon.titan-embed-text-v2:0"
COHERE = "cohere.embed-multilingual-v3"
START = datetime(2026, 11, 5, 9, 0, tzinfo=UTC)


def _client(service: str) -> Any:
    return boto3.client(  # type: ignore[call-overload]
        service,
        region_name=REGION,
        aws_access_key_id="testing",
        aws_secret_access_key="testing",  # noqa: S106
        config=Config(retries={"total_max_attempts": 1}),
    )


class StubbedAws:
    """A client factory handing out one stubbed STS and one stubbed Bedrock Runtime client,
    and recording who asked for which client, where, signed as whom."""

    def __init__(self) -> None:
        self.sts = _client("sts")
        self.sts_stub = Stubber(self.sts)
        self.runtime = _client("bedrock-runtime")
        self.runtime_stub = Stubber(self.runtime)
        self.built: list[tuple[str, str, AwsKeys | None]] = []
        self.clock = ControllableClock(START)
        self.sessions = AssumedRoleSessions(
            self.sts, self.clock, refresh_before=timedelta(minutes=5)
        )

    def __call__(self, service: str, region: str, keys: AwsKeys | None) -> Any:
        self.built.append((service, region, keys))
        assert service == "bedrock-runtime"
        return self.runtime

    def gateway(self) -> ModelGateway:
        clients = BedrockClients(self.sessions, self)
        return ModelGateway(ENVELOPE, LiveModelAdapters(httpx2.AsyncClient(), clients))

    def answer(self, model: str, sent: dict[str, Any], answer: dict[str, Any]) -> None:
        data = json.dumps(answer).encode()
        self.runtime_stub.add_response(
            "invoke_model",
            {"body": StreamingBody(io.BytesIO(data), len(data)), "contentType": "application/json"},
            {
                "modelId": model,
                "body": json.dumps(sent).encode(),
                "contentType": "application/json",
                "accept": "application/json",
            },
        )

    def assume(self, number: int) -> None:
        self.sts_stub.add_response(
            "assume_role",
            {
                "Credentials": {
                    "AccessKeyId": f"ASIATESTSESSION{number:05d}",
                    "SecretAccessKey": f"session-secret-{number}",
                    "SessionToken": f"session-token-{number}",
                    "Expiration": START + timedelta(hours=1),
                },
            },
            {
                "RoleArn": ROLE_ARN,
                "RoleSessionName": "rag-agent-studio",
                "ExternalId": EXTERNAL_ID,
                "DurationSeconds": 3600,
            },
        )


@pytest.fixture
def aws() -> Any:
    stubbed = StubbedAws()
    with stubbed.sts_stub, stubbed.runtime_stub:
        yield stubbed
        stubbed.sts_stub.assert_no_pending_responses()
        stubbed.runtime_stub.assert_no_pending_responses()


def bedrock(auth_kind: str = "aws_access_keys") -> ProviderCredential:
    organisation_id, credential_id = uuid.uuid4(), uuid.uuid4()
    keys = json.dumps({"access_key_id": ACCESS_KEY_ID, "secret_access_key": SECRET_ACCESS_KEY})
    role = auth_kind == "aws_role"
    credential = ProviderCredential(
        id=credential_id,
        organisation_id=organisation_id,
        name="Bedrock",
        provider=Provider.BEDROCK,
        auth_kind=auth_kind,
        secret_sealed=None if role else seal_secret(ENVELOPE, organisation_id, credential_id, keys),
        region=REGION,
        role_arn=ROLE_ARN if role else None,
        masked_suffix=None if role else ACCESS_KEY_ID[-4:],
        capabilities=[Capability.CHAT, Capability.EMBEDDINGS, Capability.RERANK],
        check_status="passed",
        check_failure=None,
        last_checked_at=START,
        secret_set_at=START,
    )
    credential.external_id = EXTERNAL_ID if role else None
    return credential


def titan_sent(text: str) -> dict[str, Any]:
    return {"inputText": text, "dimensions": 1024, "normalize": True}


def titan_answer(vector: list[float], tokens: int) -> dict[str, Any]:
    return {"embedding": vector, "inputTextTokenCount": tokens}


async def test_access_keys_embed_with_titan_one_text_per_call(aws: StubbedAws) -> None:
    aws.answer(TITAN, titan_sent("refund policy"), titan_answer([0.1, 0.2], 3))
    aws.answer(TITAN, titan_sent("office hours"), titan_answer([0.3, 0.4], 2))

    embedder = aws.gateway().embedder(bedrock(), TITAN)
    result = await embedder.embed(["refund policy", "office hours"], input_type="document")

    assert result.embeddings == [[0.1, 0.2], [0.3, 0.4]]
    assert result.usage.input_tokens == 5
    assert result.model_name == TITAN
    assert result.provider_name == "bedrock"
    assert embedder.model_name == TITAN
    assert embedder.system == "bedrock"
    # Signed with the credential's own access keys, in the credential's region.
    assert aws.built == [("bedrock-runtime", REGION, AwsKeys(ACCESS_KEY_ID, SECRET_ACCESS_KEY))]


@pytest.mark.parametrize(
    ("input_type", "sent"), [("document", "search_document"), ("query", "search_query")]
)
async def test_cohere_embeds_a_batch_per_call_with_its_input_type(
    aws: StubbedAws, input_type: str, sent: str
) -> None:
    aws.answer(
        COHERE,
        {"texts": ["first", "second"], "input_type": sent, "truncate": "END"},
        {
            "id": "emb-1",
            "embeddings": [[0.1, 0.2], [0.3, 0.4]],
            "texts": ["first", "second"],
            "response_type": "embeddings_floats",
        },
    )

    embedder = aws.gateway().embedder(bedrock(), COHERE)
    result = await embedder.embed(["first", "second"], input_type=input_type)  # type: ignore[arg-type]

    assert result.embeddings == [[0.1, 0.2], [0.3, 0.4]]


async def test_cohere_sends_at_most_96_texts_per_call(aws: StubbedAws) -> None:
    texts = [f"text {n}" for n in range(100)]
    for batch in (texts[:96], texts[96:]):
        aws.answer(
            COHERE,
            {"texts": batch, "input_type": "search_document", "truncate": "END"},
            {"embeddings": [[float(t.split()[1])] for t in batch]},
        )

    embedder = aws.gateway().embedder(bedrock(), COHERE)
    result = await embedder.embed(texts, input_type="document")

    assert result.embeddings == [[float(n)] for n in range(100)]


async def test_a_role_is_assumed_with_the_organisations_external_id_and_reused(
    aws: StubbedAws,
) -> None:
    aws.assume(1)  # only once: the second call reuses the cached session
    aws.answer(TITAN, titan_sent("first"), titan_answer([0.1], 1))
    aws.answer(TITAN, titan_sent("second"), titan_answer([0.2], 1))
    gateway = aws.gateway()

    first = await gateway.embedder(bedrock("aws_role"), TITAN).embed("first", input_type="query")
    second = await gateway.embedder(bedrock("aws_role"), TITAN).embed("second", input_type="query")

    assert first.embeddings == [[0.1]]
    assert second.embeddings == [[0.2]]
    session = AwsKeys(
        "ASIATESTSESSION00001",
        "session-secret-1",
        "session-token-1",
        START + timedelta(hours=1),
    )
    assert aws.built == [("bedrock-runtime", REGION, session)] * 2


async def test_a_bedrock_refusal_is_a_model_http_error(aws: StubbedAws) -> None:
    aws.runtime_stub.add_client_error(
        "invoke_model",
        service_error_code="AccessDeniedException",
        service_message="You don't have access to the model with the specified model ID.",
        http_status_code=403,
    )

    embedder = aws.gateway().embedder(bedrock(), TITAN)
    with pytest.raises(ModelHTTPError) as raised:
        await embedder.embed("refund policy", input_type="query")

    assert raised.value.status_code == 403
    assert raised.value.model_name == TITAN
    assert raised.value.body == {
        "Code": "AccessDeniedException",
        "Message": "You don't have access to the model with the specified model ID.",
    }


async def test_a_role_that_can_no_longer_be_assumed_is_a_model_http_error(
    aws: StubbedAws,
) -> None:
    aws.sts_stub.add_client_error(
        "assume_role", service_error_code="AccessDenied", http_status_code=403
    )

    embedder = aws.gateway().embedder(bedrock("aws_role"), TITAN)
    with pytest.raises(ModelHTTPError) as raised:
        await embedder.embed("refund policy", input_type="query")

    assert raised.value.status_code == 403
    assert aws.built == []


@pytest.mark.parametrize("auth_kind", ["aws_access_keys", "aws_role"])
@pytest.mark.parametrize(
    ("method", "model"),
    [("chat_model", "amazon.nova-pro-v1:0"), ("reranker", "cohere.rerank-v3-5:0")],
)
def test_bedrock_chat_and_rerank_clients_are_not_built_yet(
    aws: StubbedAws, auth_kind: str, method: str, model: str
) -> None:
    with pytest.raises(UnsupportedCredentialError, match="Bedrock"):
        getattr(aws.gateway(), method)(bedrock(auth_kind), model)


@pytest.mark.parametrize("auth_kind", ["aws_access_keys", "aws_role"])
@pytest.mark.parametrize("model", [TITAN, COHERE])
async def test_the_fake_bedrock_embedder_answers_the_models_dimension(
    auth_kind: str, model: str
) -> None:
    gateway = ModelGateway(ENVELOPE, FakeModelAdapters())

    result = await gateway.embedder(bedrock(auth_kind), model).embed("hello", input_type="query")

    (vector,) = result.embeddings
    assert len(vector) == 1024
    assert result.provider_name == "fake"


def test_the_live_gateway_assumes_roles_with_the_platforms_sts_client(
    settings_env: pytest.MonkeyPatch,
) -> None:
    settings_env.setenv("MODEL_GATEWAY", "live")
    settings_env.setenv("BEDROCK_STS_REGION", "eu-west-1")
    settings_env.setenv("BEDROCK_SESSION_REFRESH_SECONDS", "120")

    gateway = build_model_gateway(Settings(), ENVELOPE, httpx2.AsyncClient())

    assert isinstance(gateway.adapters, LiveModelAdapters)
    sessions = gateway.adapters.bedrock.sessions
    assert sessions.sts.meta.region_name == "eu-west-1"
    assert sessions.refresh_before == timedelta(seconds=120)
