"""Prefilling an Evaluation Case from an Agent Message.

An Editor turns an Agent Message, a Visitor's reply or a Playground one, into an Evaluation Case:
the question it answered becomes the case's question, and each Chunk it cited is offered as an
Expected source (the Chunk's text, up to a passage's length, of a Document that still exists).
Nothing is saved here: the Editor edits the copy before saving it, and the case keeps no link to
the Conversation or the Message (ADR-0016). Only a reply of the Agent itself can be read, and not
once its text, or its question's, has been purged.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.service import get_agent
from app.conversations.models import Conversation, Message, MessageRetrieval, MessageRole
from app.documents.models import Chunk, Document
from app.evaluation.models import PASSAGE_MAX
from app.tenancy.repository import OrganisationScope


class MessageNotFoundError(Exception):
    """No reply of this Agent with that ID."""


class MessagePurgedError(Exception):
    """The reply's text, or its question's, has been purged."""


@dataclass(frozen=True)
class OfferedSource:
    document_id: uuid.UUID
    document_name: str
    passage: str


@dataclass(frozen=True)
class Prefill:
    question: str
    # The cited passages, in the order the model was given them.
    expected_sources: list[OfferedSource]


async def _reply(session: AsyncSession, agent_id: uuid.UUID, message_id: uuid.UUID) -> Message:
    reply = await session.scalar(
        select(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Message.id == message_id,
            Message.role == MessageRole.ASSISTANT,
            Conversation.agent_id == agent_id,
        )
    )
    if reply is None:
        raise MessageNotFoundError
    return reply


async def _question(session: AsyncSession, reply: Message) -> Message:
    """The Visitor's (or Editor's) question the reply answered: the last one before it."""
    question = await session.scalar(
        select(Message)
        .where(
            Message.conversation_id == reply.conversation_id,
            Message.role == MessageRole.USER,
            Message.seq < reply.seq,
        )
        .order_by(Message.seq.desc())
        .limit(1)
    )
    if question is None:  # pragma: no cover - every reply answers a question
        raise MessageNotFoundError
    return question


async def _cited(session: AsyncSession, reply: Message) -> list[OfferedSource]:
    rows = await session.execute(
        select(Chunk.id, Chunk.text, Document.id, Document.name)
        .join(MessageRetrieval, MessageRetrieval.chunk_id == Chunk.id)
        .join(Document, Document.id == Chunk.document_id)
        .where(MessageRetrieval.message_id == reply.id, MessageRetrieval.cited.is_(True))
        .order_by(MessageRetrieval.position)
    )
    offered: dict[uuid.UUID, OfferedSource] = {}
    for chunk_id, text, document_id, name in rows:
        offered.setdefault(chunk_id, OfferedSource(document_id, name, text[:PASSAGE_MAX].strip()))
    return list(offered.values())


async def prefill(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    message_id: uuid.UUID,
) -> Prefill:
    """The question the Agent's reply ``message_id`` answered and the passages it cited.
    Refused with ``MessageNotFoundError`` for anything but a reply of this Agent, and with
    ``MessagePurgedError`` once its text or its question's has been purged."""
    found = await get_agent(session, scope, project_id, agent_id)
    reply = await _reply(session, found.agent.id, message_id)
    question = await _question(session, reply)
    if reply.purged_at is not None or question.purged_at is not None:
        raise MessagePurgedError
    return Prefill(question.content, await _cited(session, reply))
