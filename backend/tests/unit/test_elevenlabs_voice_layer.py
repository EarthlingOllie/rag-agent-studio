"""The ElevenLabs voice layer against recorded HTTP exchanges (``tests/fixtures/elevenlabs``).

No real ElevenLabs account is called: each test replays a recording, which checks every request
the adapter sends (method, URL, query and body) against the one recorded, and every request
carries the Organisation's key in ``xi-api-key``. The live suite holds the same exchanges with
a real account (``tests/live/test_elevenlabs_live.py``).
"""

import httpx
import pytest

from app.core.settings import Settings
from app.voice.adapters import build_voice_layer
from app.voice.elevenlabs import VOICES_MAX_PAGES, ElevenLabsVoiceLayer
from app.voice.port import CallJoin, RemoteAgentSpec, Voice, VoiceLayerError
from tests.fakes.http_exchanges import Replay, load

KEY = "xi-test-only-0000000000000000"

SPEC = RemoteAgentSpec(
    name="Front desk (agt_frontdesk)",
    voice_id="21m00Tcm4TlvDq8ikWAM",
    spoken_greeting="Hello, how can I help?",
    llm_url="https://calls.example.test/api/widget/agents/agt_frontdesk/llm/v1",
    llm_secret="s" * 43,
)


def replaying(recording: str) -> tuple[ElevenLabsVoiceLayer, Replay]:
    replay = Replay(load(f"elevenlabs/{recording}"))
    return ElevenLabsVoiceLayer(timeout_seconds=5, transport=replay), replay


def assert_all_sent_with_the_key(replay: Replay) -> None:
    assert replay.done
    assert {request.headers["xi-api-key"] for request in replay.seen} == {KEY}


def test_the_settings_select_elevenlabs(settings_env: pytest.MonkeyPatch) -> None:
    settings_env.setenv("VOICE_LAYER", "elevenlabs")

    assert isinstance(build_voice_layer(Settings()), ElevenLabsVoiceLayer)


async def test_a_remote_agent_is_created_with_its_secret_stored_in_the_account() -> None:
    layer, replay = replaying("create_agent.json")

    remote_agent_id = await layer.set_up_agent(KEY, SPEC, remote_agent_id=None)

    assert remote_agent_id == "agent_01k9w3"
    assert_all_sent_with_the_key(replay)


async def test_a_remote_agent_is_updated_in_place_with_its_secret() -> None:
    layer, replay = replaying("update_agent.json")

    remote_agent_id = await layer.set_up_agent(KEY, SPEC, remote_agent_id="agent_01k9w3")

    assert remote_agent_id == "agent_01k9w3"
    assert_all_sent_with_the_key(replay)


async def test_a_remote_agent_deleted_in_the_account_is_created_again() -> None:
    layer, replay = replaying("update_agent_gone.json")

    remote_agent_id = await layer.set_up_agent(KEY, SPEC, remote_agent_id="agent_gone")

    assert remote_agent_id == "agent_01kb77"
    assert_all_sent_with_the_key(replay)


async def test_a_secret_deleted_in_the_account_is_stored_again() -> None:
    layer, replay = replaying("update_agent_secret_gone.json")

    remote_agent_id = await layer.set_up_agent(KEY, SPEC, remote_agent_id="agent_01k9w3")

    assert remote_agent_id == "agent_01k9w3"
    assert_all_sent_with_the_key(replay)


async def test_a_refused_remote_agent_fails_and_leaves_no_secret_behind() -> None:
    layer, replay = replaying("create_agent_refused.json")

    with pytest.raises(VoiceLayerError):
        await layer.set_up_agent(KEY, SPEC, remote_agent_id=None)

    assert_all_sent_with_the_key(replay)


async def test_a_remote_agent_is_removed_with_its_secret() -> None:
    layer, replay = replaying("remove_agent.json")

    await layer.remove_agent(KEY, "agent_01k9w3")

    assert_all_sent_with_the_key(replay)


async def test_a_remote_agent_already_gone_counts_as_removed() -> None:
    layer, replay = replaying("remove_agent_gone.json")

    await layer.remove_agent(KEY, "agent_gone")

    assert_all_sent_with_the_key(replay)


async def test_the_voices_are_listed_page_by_page() -> None:
    layer, replay = replaying("list_voices.json")

    voices = await layer.list_voices(KEY)

    assert voices == [
        Voice(
            "21m00Tcm4TlvDq8ikWAM",
            "Rachel",
            "https://storage.googleapis.com/eleven-public-prod/premade/voices/"
            "21m00Tcm4TlvDq8ikWAM/df6788f9.mp3",
        ),
        Voice(
            "AZnzlk1XvdvUeBnXmlld",
            "Domi",
            "https://storage.googleapis.com/eleven-public-prod/premade/voices/"
            "AZnzlk1XvdvUeBnXmlld/69c5373f.mp3",
        ),
        Voice("zcAOhNBS3c14rBihAFp1", "Giovanni", None),
    ]
    assert_all_sent_with_the_key(replay)


async def test_a_call_is_started_with_a_webrtc_token() -> None:
    layer, replay = replaying("start_call.json")

    joined = await layer.start_call(KEY, "agent_01k9w3")

    assert joined == CallJoin("eyJhbGciOiJIUzI1NiJ9.livekit-room-grant")
    assert_all_sent_with_the_key(replay)


async def test_a_refused_key_fails() -> None:
    layer, replay = replaying("refused_key.json")

    with pytest.raises(VoiceLayerError):
        await layer.list_voices(KEY)

    assert replay.done


@pytest.mark.parametrize(
    "operation",
    [
        lambda layer: layer.set_up_agent(KEY, SPEC, remote_agent_id=None),
        lambda layer: layer.set_up_agent(KEY, SPEC, remote_agent_id="agent_01k9w3"),
        lambda layer: layer.remove_agent(KEY, "agent_01k9w3"),
        lambda layer: layer.list_voices(KEY),
        lambda layer: layer.start_call(KEY, "agent_01k9w3"),
    ],
)
async def test_an_unreachable_elevenlabs_fails_every_operation(operation) -> None:  # type: ignore[no-untyped-def]
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    layer = ElevenLabsVoiceLayer(timeout_seconds=5, transport=httpx.MockTransport(unreachable))

    with pytest.raises(VoiceLayerError):
        await operation(layer)


@pytest.mark.parametrize("status", [500, 503])
async def test_an_elevenlabs_outage_fails_a_call_start(status: int) -> None:
    layer = ElevenLabsVoiceLayer(
        timeout_seconds=5,
        transport=httpx.MockTransport(lambda _request: httpx.Response(status, text="Bad gateway")),
    )

    with pytest.raises(VoiceLayerError):
        await layer.start_call(KEY, "agent_01k9w3")


async def test_an_answer_that_isnt_json_fails() -> None:
    layer = ElevenLabsVoiceLayer(
        timeout_seconds=5,
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, text="<html>")),
    )

    with pytest.raises(VoiceLayerError):
        await layer.start_call(KEY, "agent_01k9w3")


def routed(
    answers: dict[tuple[str, str], httpx.Response],
) -> tuple[ElevenLabsVoiceLayer, list[str]]:
    """A layer whose ElevenLabs answers each (method, path) as given; ``sent`` lists them."""
    sent: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(f"{request.method} {request.url.path}")
        return answers[(request.method, request.url.path)]

    return ElevenLabsVoiceLayer(timeout_seconds=5, transport=httpx.MockTransport(answer)), sent


AGENT_PATH = "/v1/convai/agents/agent_01k9w3"
AGENT_WITHOUT_SECRET = {
    "agent_id": "agent_01k9w3",
    "conversation_config": {"agent": {"prompt": {"llm": "gpt-4o-mini"}}},
}


async def test_a_remote_agent_without_a_secret_gets_one_when_updated() -> None:
    layer, sent = routed(
        {
            ("GET", "/v1/convai/agents/agent_01k9w3"): httpx.Response(
                200, json=AGENT_WITHOUT_SECRET
            ),
            ("POST", "/v1/convai/secrets"): httpx.Response(200, json={"secret_id": "sec_new"}),
            ("PATCH", "/v1/convai/agents/agent_01k9w3"): httpx.Response(200, json={}),
        }
    )

    assert await layer.set_up_agent(KEY, SPEC, remote_agent_id="agent_01k9w3") == "agent_01k9w3"
    assert sent == [
        "GET /v1/convai/agents/agent_01k9w3",
        "POST /v1/convai/secrets",
        "PATCH /v1/convai/agents/agent_01k9w3",
    ]


async def test_a_remote_agent_deleted_while_it_is_updated_fails() -> None:
    layer, _ = routed(
        {
            ("GET", "/v1/convai/agents/agent_01k9w3"): httpx.Response(
                200, json=AGENT_WITHOUT_SECRET
            ),
            ("POST", "/v1/convai/secrets"): httpx.Response(200, json={"secret_id": "sec_new"}),
            ("PATCH", "/v1/convai/agents/agent_01k9w3"): httpx.Response(404, json={}),
        }
    )

    with pytest.raises(VoiceLayerError):
        await layer.set_up_agent(KEY, SPEC, remote_agent_id="agent_01k9w3")


async def test_a_remote_agent_without_a_secret_is_removed_alone() -> None:
    layer, sent = routed(
        {
            ("GET", "/v1/convai/agents/agent_01k9w3"): httpx.Response(
                200, json=AGENT_WITHOUT_SECRET
            ),
            ("DELETE", "/v1/convai/agents/agent_01k9w3"): httpx.Response(200, json={}),
        }
    )

    await layer.remove_agent(KEY, "agent_01k9w3")

    assert sent == ["GET /v1/convai/agents/agent_01k9w3", "DELETE /v1/convai/agents/agent_01k9w3"]


async def test_a_secret_already_gone_counts_as_removed() -> None:
    layer, sent = routed(
        {
            ("GET", "/v1/convai/agents/agent_01k9w3"): httpx.Response(
                200, json=load("elevenlabs/remove_agent.json")[0]["response"]["json"]
            ),
            ("DELETE", "/v1/convai/agents/agent_01k9w3"): httpx.Response(200, json={}),
            ("DELETE", "/v1/convai/secrets/sec_7Hq2"): httpx.Response(404, json={}),
        }
    )

    await layer.remove_agent(KEY, "agent_01k9w3")

    assert sent[-1] == "DELETE /v1/convai/secrets/sec_7Hq2"


async def test_a_call_with_a_remote_agent_gone_fails() -> None:
    layer, _ = routed(
        {("GET", "/v1/convai/conversation/token"): httpx.Response(404, json={"detail": {}})}
    )

    with pytest.raises(VoiceLayerError):
        await layer.start_call(KEY, "agent_gone")


async def test_voices_stop_after_the_last_page_read() -> None:
    endless = {
        "voices": [{"voice_id": "v1", "name": None}],
        "has_more": True,
        "next_page_token": "more",
    }
    layer, sent = routed({("GET", "/v2/voices"): httpx.Response(200, json=endless)})

    voices = await layer.list_voices(KEY)

    assert len(sent) == VOICES_MAX_PAGES
    assert voices[0] == Voice("v1", "v1", None)
