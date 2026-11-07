"""Widget routes for Message Feedback, under the widget API. They are authenticated by the
Conversation token (``Authorization: Bearer …``), so a Visitor can only give feedback on replies
in their own Conversation; any other Message is not found."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, StringConstraints

from app.agents.api import ClockDep
from app.auth.api import Db
from app.embed import service as embed
from app.embed.api import INVALID_TOKEN, Authorization, Signer, _bearer, _errors, _invalid
from app.feedback import service
from app.feedback.models import COMMENT_MAX, Thumb

REPLY_NOT_FOUND = "There is no such reply in this chat."

widget_router = APIRouter(
    prefix="/api/widget/agents/{public_id}/messages/{message_id}/feedback", tags=["widget"]
)


class MessageFeedbackIn(BaseModel):
    rating: Literal["up", "down"]
    # Optional; blank counts as none.
    comment: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=COMMENT_MAX)] | None
    ) = Field(default=None)


class MessageFeedbackOut(BaseModel):
    rating: Literal["up", "down"]
    comment: str | None


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, REPLY_NOT_FOUND)


_RESPONSES = _errors((401, INVALID_TOKEN), (404, REPLY_NOT_FOUND))


@widget_router.put("", operation_id="giveMessageFeedback", responses=_RESPONSES)
async def give_feedback(
    public_id: str,
    message_id: uuid.UUID,
    body: MessageFeedbackIn,
    db: Db,
    signer: Signer,
    clock: ClockDep,
    authorization: Authorization = "",
) -> MessageFeedbackOut:
    """Gives a thumbs up or down, with an optional comment, on one of the Agent's replies in the
    token's Conversation; giving it again replaces it. The feedback belongs to the Agent Version
    that gave the reply."""
    now = clock.now()
    try:
        conversation = await embed.visitor_conversation(
            db, signer, public_id, _bearer(authorization), now=now
        )
        given = await service.give(
            db,
            conversation,
            message_id,
            service.Feedback(Thumb(body.rating), body.comment or None),
            now=now,
        )
    except embed.InvalidTokenError:
        raise _invalid() from None
    except service.ReplyNotFoundError:
        raise _not_found() from None
    return MessageFeedbackOut(rating=given.rating.value, comment=given.comment)


@widget_router.delete(
    "", operation_id="removeMessageFeedback", status_code=204, responses=_RESPONSES
)
async def remove_feedback(
    public_id: str,
    message_id: uuid.UUID,
    db: Db,
    signer: Signer,
    clock: ClockDep,
    authorization: Authorization = "",
) -> None:
    """Removes the Visitor's feedback on one of the Agent's replies in the token's
    Conversation (nothing happens when there is none)."""
    try:
        conversation = await embed.visitor_conversation(
            db, signer, public_id, _bearer(authorization), now=clock.now()
        )
        await service.remove(db, conversation, message_id)
    except embed.InvalidTokenError:
        raise _invalid() from None
    except service.ReplyNotFoundError:
        raise _not_found() from None
