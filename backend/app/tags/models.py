"""Tags and the Tags applied to Documents. A Tag belongs to one Project; its name is unique in
the Project, ignoring case. Both tables carry the Organisation and Project (ADR-0001)."""

import uuid

from sqlalchemy import ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin
from app.documents.models import Document
from app.projects.models import Project
from app.tenancy.models import Organisation

TAG_NAME_MAX = 50


class Tag(IdMixin, Base):
    __tablename__ = "tags"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Organisation.id, ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Project.id, ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(TAG_NAME_MAX))


# Names are unique in a Project, ignoring case.
Index("uq_tags_project_name", Tag.project_id, func.lower(Tag.name), unique=True)


class DocumentTag(Base):
    """A Tag applied to a Document. Deleting either removes it."""

    __tablename__ = "document_tags"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Organisation.id, ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Document.id, ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(Tag.id, ondelete="CASCADE"), primary_key=True, index=True
    )
