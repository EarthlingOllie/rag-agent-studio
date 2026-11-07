"""Studio routes for the Conversations viewer: a Project's Conversations, filtered, and one
Conversation with its Messages and each reply's Trace. Editors and Owners may use them.

Playground Conversations are listed beside Visitor ones and flagged with ``is_playground``."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import AwareDatetime, BaseModel

from app.agents.api import NOT_FOUND_RESPONSE, not_found
from app.auth.api import Db
from app.conversations import service
from app.playground.api import (
    MessageOut,
    TraceOut,
    instructions_numbers,
    message_fields,
    trace_out,
)
from app.projects.service import ProjectNotFoundError
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import Scope

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
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 25,
) -> ConversationPageOut:
    """The Project's Conversations, Visitors' and the Playground's, newest first."""
    where = service.ConversationFilter(
        agent_id=agent_id, version_id=version_id, start=start, end=end, playground=playground
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
            )
            for row in result.rows
        ],
        page=page,
        page_size=page_size,
        total=result.total,
    )


class ConversationMessageOut(MessageOut):
    # The number of the Agent Version that answered; null for questions and Draft answers.
    agent_version_number: int | None
    # True when the answer is the Agent's fallback text (no Chunk reached the minimum score).
    fallback: bool


class ConversationDetailOut(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    agent_name: str
    is_playground: bool
    created_at: datetime
    last_activity_at: datetime
    messages: list[ConversationMessageOut]


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
            )
            for m in read.messages
        ],
    )


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
