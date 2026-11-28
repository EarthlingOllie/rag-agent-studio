"""The scripted fake voice layer's own route (``VOICE_LAYER=fake`` only; not in the API client).

It stands in for the audio connection a browser holds with ElevenLabs: the widget's scripted
call client posts the words it "says" in a Call, and the fake voice layer holds the turn as
ElevenLabs would, through the turn endpoint, and answers with the reply it would speak. With
another voice layer the route is not found.
"""

from typing import Annotated

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, StringConstraints

from app.playground.api import QUESTION_MAX
from app.voice.fake import FakeVoiceLayer
from app.voice.port import VoiceLayerError

router = APIRouter(prefix="/api/widget/fake-voice", include_in_schema=False)


class FakeTurnIn(BaseModel):
    words: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=QUESTION_MAX)
    ]
    call_token: Annotated[str, StringConstraints(max_length=1000)]


class FakeTurnOut(BaseModel):
    # What the voice layer would speak.
    agent_response: str


@router.post("/calls/{join_token}/turns")
async def hold_turn(join_token: str, body: FakeTurnIn, request: Request) -> FakeTurnOut:
    layer = request.app.state.voice_layer
    if not isinstance(layer, FakeVoiceLayer):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    try:
        reply = await layer.hold_turn(
            join_token, body.words, body.call_token, transport=httpx.ASGITransport(app=request.app)
        )
    except VoiceLayerError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from None
    return FakeTurnOut(agent_response=reply)
