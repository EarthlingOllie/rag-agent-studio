"""Widget routes for Message Feedback and the Conversation Rating, under the widget API. They are
authenticated by the Conversation token (``Authorization: Bearer …``), so a Visitor can only give
feedback on replies in their own Conversation (any other Message is not found) and only rate
their own Conversation."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, StringConstraints

from app.agents.api import ClockDep
from app.auth.api import Db
from app.embed import service as embed
from app.embed.api import INVALID_TOKEN, Authorization, Signer, _bearer, _errors, _invalid
from app.feedback import service
from app.feedback.models import COMMENT_MAX, SCORE_MAX, SCORE_MIN, Thumb

REPLY_NOT_FOUND = "There is no such reply in this chat."
NOTHING_TO_RATE = "There is nothing to rate yet."

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


# The Conversation Rating


rating_router = APIRouter(
    prefix="/api/widget/agents/{public_id}/conversation/rating", tags=["widget"]
)


class ConversationRatingIn(BaseModel):
    score: Annotated[int, Field(strict=True, ge=SCORE_MIN, le=SCORE_MAX)]


class ConversationRatingOut(BaseModel):
    # 1 to 5.
    score: int
    # True once the Visitor dismissed the rating prompt in this Conversation.
    prompt_dismissed: bool


@rating_router.put(
    "",
    operation_id="rateConversation",
    responses=_errors((401, INVALID_TOKEN), (409, NOTHING_TO_RATE)),
)
async def rate_conversation(
    public_id: str,
    body: ConversationRatingIn,
    db: Db,
    signer: Signer,
    clock: ClockDep,
    authorization: Authorization = "",
) -> ConversationRatingOut:
    """Rates the token's Conversation from 1 to 5, or changes its rating; the first rating and
    each change are kept in a change log. The rating belongs to the Agent Version of the last
    reply before it. Refused until the Agent has replied."""
    now = clock.now()
    try:
        conversation = await embed.visitor_conversation(
            db, signer, public_id, _bearer(authorization), now=now
        )
        rated = await service.rate(db, conversation, body.score, now=now)
    except embed.InvalidTokenError:
        raise _invalid() from None
    except service.NothingToRateError:
        raise HTTPException(status.HTTP_409_CONFLICT, NOTHING_TO_RATE) from None
    return ConversationRatingOut(score=body.score, prompt_dismissed=rated.prompt_dismissed)


@rating_router.post(
    "/dismissal",
    operation_id="dismissRatingPrompt",
    status_code=204,
    responses=_errors((401, INVALID_TOKEN)),
)
async def dismiss_rating_prompt(
    public_id: str,
    db: Db,
    signer: Signer,
    clock: ClockDep,
    authorization: Authorization = "",
) -> None:
    """Saves that the Visitor dismissed the rating prompt, so the widget doesn't show it again
    in this Conversation (it still asks when they end the chat without a rating)."""
    now = clock.now()
    try:
        conversation = await embed.visitor_conversation(
            db, signer, public_id, _bearer(authorization), now=now
        )
    except embed.InvalidTokenError:
        raise _invalid() from None
    await service.dismiss_prompt(db, conversation, now=now)
