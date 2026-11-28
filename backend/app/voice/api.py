"""Voice layer routes: a voice-capable credential's voices, for the Studio's voice picker. Open to
every Member; another Organisation's credential is not found.

``get_voice_ports`` gives other modules' routes what they need to keep remote agents in step.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select

from app.auth.api import Db, ErrorResponse
from app.core.settings import Settings
from app.credentials.models import ProviderCredential
from app.credentials.registry import Capability
from app.credentials.service import open_secret
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import NOT_FOUND, Scope
from app.voice.port import VoiceLayerError
from app.voice.remote import VoicePorts

router = APIRouter(prefix=ORGANISATION_PREFIX, tags=["voice"])

NOT_VOICE_CAPABLE = "This credential doesn't have the voice Capability, so it has no voices."
VOICE_LAYER_FAILED = (
    "ElevenLabs couldn't be reached with this credential. Check the credential in Organisation "
    "settings, Credentials, or try again shortly."
)


def get_voice_ports(request: Request) -> VoicePorts:
    state = request.app.state
    settings: Settings = state.settings
    return VoicePorts(
        layer=state.voice_layer,
        envelope=state.envelope,
        public_base_url=str(settings.public_base_url or settings.studio_url),
    )


Voice = Annotated[VoicePorts, Depends(get_voice_ports)]


def voice_layer_failed() -> HTTPException:
    return HTTPException(status.HTTP_502_BAD_GATEWAY, VOICE_LAYER_FAILED)


class VoiceOut(BaseModel):
    id: str
    name: str
    # A short recording to listen to, when the account has one.
    sample_url: str | None


_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": NOT_FOUND},
    422: {"model": ErrorResponse, "description": NOT_VOICE_CAPABLE},
    502: {"model": ErrorResponse, "description": VOICE_LAYER_FAILED},
}


@router.get("/credentials/{credential_id}/voices", responses=_RESPONSES, operation_id="listVoices")
async def list_voices(
    credential_id: uuid.UUID, scope: Scope, db: Db, voice: Voice
) -> list[VoiceOut]:
    """The voices the credential's ElevenLabs account offers, for the voice picker."""
    credential = await db.scalar(
        select(ProviderCredential).where(
            ProviderCredential.id == credential_id,
            ProviderCredential.organisation_id == scope.organisation_id,
        )
    )
    if credential is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    if Capability.VOICE not in credential.capabilities:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, NOT_VOICE_CAPABLE)
    try:
        voices = await voice.layer.list_voices(open_secret(voice.envelope, credential))
    except VoiceLayerError:
        raise voice_layer_failed() from None
    return [VoiceOut(id=v.id, name=v.name, sample_url=v.sample_url) for v in voices]
