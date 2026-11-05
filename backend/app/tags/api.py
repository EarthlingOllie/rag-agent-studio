"""Tag routes: a Project's Tags (list, create, rename, delete), setting one Document's Tags,
and bulk-tagging many Documents. Any Member may use them; an archived Project's Tags can be
read but not changed."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, StringConstraints

from app.auth.api import Db, ErrorResponse
from app.projects.api import PROJECT_ARCHIVED
from app.projects.service import ProjectArchivedError, ProjectNotFoundError
from app.tags import service
from app.tags.models import TAG_NAME_MAX, Tag
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import NOT_FOUND, Scope

router = APIRouter(prefix=ORGANISATION_PREFIX + "/projects/{project_id}", tags=["tags"])

DUPLICATE_TAG = "This Project already has a Tag with that name."
UNKNOWN_TAGS = "One or more of these Tags aren't in this Project."
UNKNOWN_DOCUMENTS = "One or more of these Documents aren't in this Project."

# How many Documents one bulk-tagging request may change.
BULK_MAX = 500

TagName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TAG_NAME_MAX)
]


def _errors(*codes: tuple[int, str]) -> dict[int | str, dict[str, Any]]:
    return {code: {"model": ErrorResponse, "description": text} for code, text in codes}


_NOT_FOUND = (404, NOT_FOUND)
_ARCHIVED = (409, PROJECT_ARCHIVED)


class TagRef(BaseModel):
    """A Tag as shown on a Document."""

    id: uuid.UUID
    name: str


class TagOut(BaseModel):
    id: uuid.UUID
    name: str
    # How many of the Project's Documents carry the Tag.
    document_count: int
    created_at: datetime


class TagRequest(BaseModel):
    name: TagName


class DocumentTagsRequest(BaseModel):
    # The Document's Tags after the change; an empty list removes them all.
    tag_ids: list[uuid.UUID] = Field(max_length=100)


class BulkTagRequest(BaseModel):
    document_ids: list[uuid.UUID] = Field(min_length=1, max_length=BULK_MAX)
    # Tags to apply to every listed Document.
    add: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    # Tags to take off every listed Document. A Tag in both lists is taken off.
    remove: list[uuid.UUID] = Field(default_factory=list, max_length=100)


def tag_ref(tag: Tag) -> TagRef:
    return TagRef(id=tag.id, name=tag.name)


def _out(summary: service.TagSummary) -> TagOut:
    tag = summary.tag
    return TagOut(
        id=tag.id, name=tag.name, document_count=summary.document_count, created_at=tag.created_at
    )


@router.get("/tags", operation_id="listTags", responses=_errors(_NOT_FOUND))
async def list_tags(project_id: uuid.UUID, scope: Scope, db: Db) -> list[TagOut]:
    """The Project's Tags by name, with how many Documents carry each."""
    try:
        summaries = await service.list_tags(db, scope, project_id)
    except ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    return [_out(s) for s in summaries]


@router.post(
    "/tags",
    status_code=status.HTTP_201_CREATED,
    operation_id="createTag",
    responses=_errors(_NOT_FOUND, (409, f"{DUPLICATE_TAG} / {PROJECT_ARCHIVED}")),
)
async def create_tag(project_id: uuid.UUID, body: TagRequest, scope: Scope, db: Db) -> TagOut:
    """Creates a Tag. Names are unique in the Project, ignoring case."""
    try:
        summary = await service.create_tag(db, scope, project_id, name=body.name)
    except ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    except ProjectArchivedError:
        raise HTTPException(status.HTTP_409_CONFLICT, PROJECT_ARCHIVED) from None
    except service.DuplicateTagNameError:
        raise HTTPException(status.HTTP_409_CONFLICT, DUPLICATE_TAG) from None
    return _out(summary)


@router.patch(
    "/tags/{tag_id}",
    operation_id="renameTag",
    responses=_errors(_NOT_FOUND, (409, f"{DUPLICATE_TAG} / {PROJECT_ARCHIVED}")),
)
async def rename_tag(
    project_id: uuid.UUID, tag_id: uuid.UUID, body: TagRequest, scope: Scope, db: Db
) -> TagOut:
    """Renames a Tag. Documents keep it."""
    try:
        summary = await service.rename_tag(db, scope, project_id, tag_id, name=body.name)
    except (ProjectNotFoundError, service.TagNotFoundError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    except ProjectArchivedError:
        raise HTTPException(status.HTTP_409_CONFLICT, PROJECT_ARCHIVED) from None
    except service.DuplicateTagNameError:
        raise HTTPException(status.HTTP_409_CONFLICT, DUPLICATE_TAG) from None
    return _out(summary)


@router.delete(
    "/tags/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteTag",
    responses=_errors(_NOT_FOUND, _ARCHIVED),
)
async def delete_tag(project_id: uuid.UUID, tag_id: uuid.UUID, scope: Scope, db: Db) -> None:
    """Deletes a Tag and takes it off every Document. The Documents stay."""
    try:
        await service.delete_tag(db, scope, project_id, tag_id)
    except (ProjectNotFoundError, service.TagNotFoundError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    except ProjectArchivedError:
        raise HTTPException(status.HTTP_409_CONFLICT, PROJECT_ARCHIVED) from None


@router.put(
    "/documents/{document_id}/tags",
    operation_id="setDocumentTags",
    responses=_errors(_NOT_FOUND, _ARCHIVED, (422, UNKNOWN_TAGS)),
)
async def set_document_tags(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    body: DocumentTagsRequest,
    scope: Scope,
    db: Db,
) -> list[TagRef]:
    """Sets the Document's Tags to exactly the ones given; answers with them, by name."""
    try:
        await service.set_document_tags(db, scope, project_id, document_id, body.tag_ids)
    except (ProjectNotFoundError, service.UnknownDocumentsError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    except ProjectArchivedError:
        raise HTTPException(status.HTTP_409_CONFLICT, PROJECT_ARCHIVED) from None
    except service.UnknownTagsError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, UNKNOWN_TAGS) from None
    tags = await service.tags_of(db, [document_id])
    return [tag_ref(tag) for tag in tags.get(document_id, [])]


@router.post(
    "/documents/tags",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="bulkTagDocuments",
    responses=_errors(_NOT_FOUND, _ARCHIVED, (422, f"{UNKNOWN_TAGS} / {UNKNOWN_DOCUMENTS}")),
)
async def bulk_tag_documents(
    project_id: uuid.UUID, body: BulkTagRequest, scope: Scope, db: Db
) -> None:
    """Applies Tags to, and takes Tags off, many Documents at once."""
    try:
        await service.bulk_tag(
            db, scope, project_id, document_ids=body.document_ids, add=body.add, remove=body.remove
        )
    except ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    except ProjectArchivedError:
        raise HTTPException(status.HTTP_409_CONFLICT, PROJECT_ARCHIVED) from None
    except service.UnknownTagsError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, UNKNOWN_TAGS) from None
    except service.UnknownDocumentsError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, UNKNOWN_DOCUMENTS) from None
