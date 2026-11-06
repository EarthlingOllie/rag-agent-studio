"""A Project's Tags: create, rename, delete, and apply them to Documents.

Every function takes the Organisation scope and finds the Project only inside it. Changing
Tags goes through ``active_project``, so an archived Project's Tags can be read but not
changed. A Tag or Document ID from another Project is treated as not found.
"""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.models import Document
from app.projects import service as projects
from app.projects.models import Project
from app.tags.models import DocumentTag, Tag
from app.tenancy.repository import OrganisationScope


class TagNotFoundError(Exception):
    """No Tag with that ID in the Project."""


class DuplicateTagNameError(Exception):
    """The Project already has a Tag with that name, ignoring case."""


class UnknownTagsError(Exception):
    """One or more Tag IDs aren't Tags of the Project."""


class UnknownDocumentsError(Exception):
    """One or more Document IDs aren't Documents of the Project."""


@dataclass(frozen=True)
class TagSummary:
    tag: Tag
    document_count: int


async def list_tags(
    session: AsyncSession, scope: OrganisationScope, project_id: uuid.UUID
) -> list[TagSummary]:
    """The Project's Tags by name, with how many Documents carry each."""
    project = await projects.get_project(session, scope, project_id)
    count = (
        select(func.count()).where(DocumentTag.tag_id == Tag.id).correlate(Tag).scalar_subquery()
    )
    rows = await session.execute(
        select(Tag, count)
        .where(Tag.project_id == project.id)
        .order_by(func.lower(Tag.name), Tag.created_at)
    )
    return [TagSummary(tag, document_count) for tag, document_count in rows]


async def _summary(session: AsyncSession, tag: Tag) -> TagSummary:
    count = await session.scalar(
        select(func.count()).select_from(DocumentTag).where(DocumentTag.tag_id == tag.id)
    )
    return TagSummary(tag, count or 0)


async def _commit_unique(session: AsyncSession) -> None:
    """Commits; a name already used in the Project, ignoring case, hits the unique index."""
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise DuplicateTagNameError from None


async def create_tag(
    session: AsyncSession, scope: OrganisationScope, project_id: uuid.UUID, *, name: str
) -> TagSummary:
    project = await projects.active_project(session, scope, project_id)
    tag = Tag(organisation_id=scope.organisation_id, project_id=project.id, name=name)
    session.add(tag)
    await _commit_unique(session)
    await session.refresh(tag)
    return TagSummary(tag, 0)


async def _tag(session: AsyncSession, project: Project, tag_id: uuid.UUID) -> Tag:
    tag = await session.scalar(select(Tag).where(Tag.id == tag_id, Tag.project_id == project.id))
    if tag is None:
        raise TagNotFoundError
    return tag


async def rename_tag(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    tag_id: uuid.UUID,
    *,
    name: str,
) -> TagSummary:
    """Renames the Tag; Documents and Agents keep it, since they refer to it by ID."""
    project = await projects.active_project(session, scope, project_id)
    tag = await _tag(session, project, tag_id)
    tag.name = name
    await _commit_unique(session)
    return await _summary(session, tag)


async def delete_tag(
    session: AsyncSession, scope: OrganisationScope, project_id: uuid.UUID, tag_id: uuid.UUID
) -> None:
    """Deletes the Tag and removes it from every Document; the Documents stay."""
    project = await projects.active_project(session, scope, project_id)
    tag = await _tag(session, project, tag_id)
    await session.delete(tag)
    await session.commit()


async def _project_tag_ids(
    session: AsyncSession, project: Project, tag_ids: Iterable[uuid.UUID]
) -> set[uuid.UUID]:
    wanted = set(tag_ids)
    found = set(
        await session.scalars(
            select(Tag.id).where(Tag.project_id == project.id, Tag.id.in_(wanted))
        )
    )
    if found != wanted:
        raise UnknownTagsError
    return found


async def _project_document_ids(
    session: AsyncSession, project: Project, document_ids: Iterable[uuid.UUID]
) -> set[uuid.UUID]:
    wanted = set(document_ids)
    found = set(
        await session.scalars(
            select(Document.id).where(Document.project_id == project.id, Document.id.in_(wanted))
        )
    )
    if found != wanted:
        raise UnknownDocumentsError
    return found


async def _add(
    session: AsyncSession,
    scope: OrganisationScope,
    document_ids: set[uuid.UUID],
    tag_ids: set[uuid.UUID],
) -> None:
    if not document_ids or not tag_ids:
        return
    rows = [
        {"organisation_id": scope.organisation_id, "document_id": d, "tag_id": t}
        for d in document_ids
        for t in tag_ids
    ]
    await session.execute(insert(DocumentTag).values(rows).on_conflict_do_nothing())


async def set_document_tags(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    tag_ids: Sequence[uuid.UUID],
) -> None:
    """Replaces the Document's Tags with exactly ``tag_ids``."""
    project = await projects.active_project(session, scope, project_id)
    (document,) = await _project_document_ids(session, project, [document_id])
    tags = await _project_tag_ids(session, project, tag_ids)
    await session.execute(
        delete(DocumentTag).where(
            DocumentTag.document_id == document, DocumentTag.tag_id.not_in(tags)
        )
    )
    await _add(session, scope, {document}, tags)
    await session.commit()


async def bulk_tag(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    *,
    document_ids: Sequence[uuid.UUID],
    add: Sequence[uuid.UUID],
    remove: Sequence[uuid.UUID],
) -> None:
    """Applies ``add`` to every listed Document and takes ``remove`` off them, in one step.
    Tags the Documents already have, or don't have, are left as they are."""
    project = await projects.active_project(session, scope, project_id)
    documents = await _project_document_ids(session, project, document_ids)
    added = await _project_tag_ids(session, project, add)
    removed = await _project_tag_ids(session, project, remove)
    if removed:
        await session.execute(
            delete(DocumentTag).where(
                DocumentTag.document_id.in_(documents), DocumentTag.tag_id.in_(removed)
            )
        )
    await _add(session, scope, documents, added - removed)
    await session.commit()


async def tags_of(
    session: AsyncSession, document_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, list[Tag]]:
    """Each Document's Tags, by name."""
    rows = await session.execute(
        select(DocumentTag.document_id, Tag)
        .join(Tag, Tag.id == DocumentTag.tag_id)
        .where(DocumentTag.document_id.in_(list(document_ids)))
        .order_by(func.lower(Tag.name), Tag.created_at)
    )
    found: dict[uuid.UUID, list[Tag]] = {}
    for document_id, tag in rows:
        found.setdefault(document_id, []).append(tag)
    return found
