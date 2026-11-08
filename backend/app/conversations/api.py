"""Studio routes for the Conversations viewer: a Project's Conversations, filtered, and one
Conversation with its Messages and each reply's Trace. Editors and Owners may use them; only
Owners may delete a Conversation on request.

Playground Conversations are listed beside Visitor ones and flagged with ``is_playground``."""

import uuid
from datetime import datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import AwareDatetime, BaseModel

from app.agents.api import NOT_FOUND_RESPONSE, not_found
from app.auth.api import Db
from app.conversations import service
from app.core.clock import Clock, get_clock
from app.feedback.models import MessageFeedback
from app.playground.api import (
    MessageOut,
    TraceOut,
    instructions_numbers,
    message_fields,
    trace_out,
)
from app.projects.service import ProjectNotFoundError
from app.retention import service as retention
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import OwnerScope, Scope

router = APIRouter(
    prefix=ORGANISATION_PREFIX + "/projects/{project_id}/conversations", tags=["conversations"]
)

MAX_PAGE_SIZE = 100


class ConversationSummaryOut(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    agent_name: str
    # True for a Conversation an Editor had in the Playground, False for a Visitor's.
    is_playground: bool
    created_at: datetime
    last_activity_at: datetime
    message_count: int
    # The first question, cut to 120 characters; null when nothing has been asked yet.
    preview: str | None
    # The numbers of the Agent Versions that answered, ascending; empty in the Playground.
    version_numbers: list[int]
    # How many of its replies the Visitor gave a thumbs up, and a thumbs down.
    thumbs_up: int
    thumbs_down: int
    # Its current Conversation Rating, 1 to 5; null when the Visitor hasn't rated it.
    rating: int | None
    # When an Owner deleted it on request (its text is purged); null otherwise.
    deleted_at: datetime | None


class ConversationPageOut(BaseModel):
    items: list[ConversationSummaryOut]
    page: int
    page_size: int
    total: int


@router.get("", operation_id="listConversations", responses=NOT_FOUND_RESPONSE)
async def list_conversations(
    project_id: uuid.UUID,
    scope: Scope,
    db: Db,
    agent_id: Annotated[uuid.UUID | None, Query(description="Only this Agent's")] = None,
    version_id: Annotated[
        uuid.UUID | None, Query(description="Only those with a reply from this Agent Version")
    ] = None,
    start: Annotated[
        AwareDatetime | None, Query(description="Only those started at or after this time")
    ] = None,
    end: Annotated[
        AwareDatetime | None, Query(description="Only those started before this time")
    ] = None,
    playground: Annotated[
        bool | None,
        Query(description="true: only Playground Conversations; false: only Visitors'"),
    ] = None,
    feedback: Annotated[
        service.FeedbackFilter | None,
        Query(
            description=(
                "Only those with a reply given a thumbs up (`up`) or down (`down`), with any "
                "Message Feedback (`any`), or with none (`none`)"
            )
        ),
    ] = None,
    rating: Annotated[
        service.RatingFilter | None,
        Query(
            description=(
                "Only those whose Conversation Rating is this score (`1` to `5`), rated with "
                "any score (`any`), or not rated (`none`)"
            )
        ),
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 25,
) -> ConversationPageOut:
    """The Project's Conversations, Visitors' and the Playground's, newest first."""
    where = service.ConversationFilter(
        agent_id=agent_id,
        version_id=version_id,
        start=start,
        end=end,
        playground=playground,
        feedback=feedback,
        rating=rating,
    )
    try:
        result = await service.list_conversations(
            db, scope, project_id, where, page=page, size=page_size
        )
    except ProjectNotFoundError:
        raise not_found() from None
    return ConversationPageOut(
        items=[
            ConversationSummaryOut(
                id=row.conversation.id,
                agent_id=row.conversation.agent_id,
                agent_name=row.agent_name,
                is_playground=row.conversation.is_playground,
                created_at=row.conversation.created_at,
                last_activity_at=row.conversation.last_activity_at,
                message_count=row.message_count,
                preview=row.preview,
                version_numbers=row.version_numbers,
                thumbs_up=row.thumbs_up,
                thumbs_down=row.thumbs_down,
                rating=row.rating,
                deleted_at=row.conversation.deleted_at,
            )
            for row in result.rows
        ],
        page=page,
        page_size=page_size,
        total=result.total,
    )


class MessageFeedbackRead(BaseModel):
    rating: Literal["up", "down"]
    comment: str | None
    # The Agent Version the feedback is attributed to: the reply's, stored when it was given.
    agent_version_number: int | None
    # When the Visitor gave it, or last changed it.
    updated_at: datetime


class ConversationMessageOut(MessageOut):
    # The number of the Agent Version that answered; null for questions and Draft answers.
    agent_version_number: int | None
    # True when the answer is the Agent's fallback text (no Chunk reached the minimum score).
    fallback: bool
    # The Visitor's Message Feedback on a reply; null when none was given.
    feedback: MessageFeedbackRead | None
    # When its text (and any feedback comment) was purged, by the Retention Window or the
    # Conversation's deletion: ``content`` is then empty. Null while it is kept.
    purged_at: datetime | None


class RatingChangeRead(BaseModel):
    score: int
    # The score before; null for the first rating.
    previous_score: int | None
    # The Agent Version of the last reply before this change, stored when it was made.
    agent_version_number: int | None
    changed_at: datetime


class ConversationRatingRead(BaseModel):
    # The current score, 1 to 5; null when the Visitor only dismissed the prompt.
    score: int | None
    # The Agent Version the rating is attributed to: that of the last reply before the rating
    # or its latest change.
    agent_version_number: int | None
    # When the Visitor rated, or last changed the rating.
    rated_at: datetime | None
    # When the Visitor dismissed the rating prompt; null when they never did.
    prompt_dismissed_at: datetime | None
    # Every rating given, oldest first: the first rating, then each change.
    changes: list[RatingChangeRead]


class ConversationDetailOut(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    agent_name: str
    is_playground: bool
    created_at: datetime
    last_activity_at: datetime
    messages: list[ConversationMessageOut]
    # The Visitor's Conversation Rating; null when they neither rated nor dismissed the prompt.
    rating: ConversationRatingRead | None
    # When an Owner deleted it on request (its text is purged); null otherwise.
    deleted_at: datetime | None


def _number(version_id: uuid.UUID | None, numbers: dict[uuid.UUID, int]) -> int | None:
    return None if version_id is None else numbers[version_id]


def _rating_read(read: service.ConversationRead) -> ConversationRatingRead | None:
    rating = read.rating
    if rating is None:
        return None
    return ConversationRatingRead(
        score=rating.score,
        agent_version_number=_number(rating.agent_version_id, read.version_numbers),
        rated_at=rating.rated_at,
        prompt_dismissed_at=rating.prompt_dismissed_at,
        changes=[
            RatingChangeRead(
                score=change.score,
                previous_score=change.previous_score,
                agent_version_number=_number(change.agent_version_id, read.version_numbers),
                changed_at=change.changed_at,
            )
            for change in read.rating_changes
        ],
    )


def _feedback_read(
    feedback: MessageFeedback | None, numbers: dict[uuid.UUID, int]
) -> MessageFeedbackRead | None:
    if feedback is None:
        return None
    return MessageFeedbackRead(
        rating=cast(Literal["up", "down"], feedback.rating),
        comment=feedback.comment,
        agent_version_number=(
            None if feedback.agent_version_id is None else numbers[feedback.agent_version_id]
        ),
        updated_at=feedback.updated_at,
    )


_DETAIL_NOT_FOUND = (
    ProjectNotFoundError,
    service.ConversationNotFoundError,
    service.MessageNotFoundError,
)


@router.get("/{conversation_id}", operation_id="getConversation", responses=NOT_FOUND_RESPONSE)
async def get_conversation(
    project_id: uuid.UUID, conversation_id: uuid.UUID, scope: Scope, db: Db
) -> ConversationDetailOut:
    """The Conversation and its Messages, oldest first, with the Agent Version of each
    answer."""
    try:
        read = await service.get_conversation(db, scope, project_id, conversation_id)
    except _DETAIL_NOT_FOUND:
        raise not_found() from None
    conversation, numbers = read.conversation, await instructions_numbers(db, read.messages)
    return ConversationDetailOut(
        id=conversation.id,
        agent_id=conversation.agent_id,
        agent_name=read.agent_name,
        is_playground=conversation.is_playground,
        created_at=conversation.created_at,
        last_activity_at=conversation.last_activity_at,
        messages=[
            ConversationMessageOut(
                **message_fields(m, numbers),
                agent_version_number=(
                    None if m.agent_version_id is None else read.version_numbers[m.agent_version_id]
                ),
                fallback=m.fallback,
                feedback=_feedback_read(read.feedback.get(m.id), read.version_numbers),
                purged_at=m.purged_at,
            )
            for m in read.messages
        ],
        rating=_rating_read(read),
        deleted_at=conversation.deleted_at,
    )


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    operation_id="deleteConversation",
    responses=NOT_FOUND_RESPONSE,
)
async def delete_conversation(
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    scope: OwnerScope,
    db: Db,
    clock: Annotated[Clock, Depends(get_clock)],
) -> None:
    """Deletes the Conversation on request (Owners only): its Messages' text and feedback
    comments are purged at once and its Conversation token stops working; its numbers stay in
    the metrics. Recorded as ``conversation.deleted``."""
    try:
        await retention.delete_conversation(db, scope, project_id, conversation_id, now=clock.now())
    except (ProjectNotFoundError, service.ConversationNotFoundError):
        raise not_found() from None


@router.get(
    "/{conversation_id}/messages/{message_id}/trace",
    operation_id="getConversationTrace",
    responses=NOT_FOUND_RESPONSE,
)
async def get_trace(
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    scope: Scope,
    db: Db,
) -> TraceOut:
    """The Trace of one of the Agent's answers in the Conversation."""
    try:
        read = await service.get_trace(db, scope, project_id, conversation_id, message_id)
    except _DETAIL_NOT_FOUND:
        raise not_found() from None
    return await trace_out(db, read.message, read.agent_version_number, read.chunks)
