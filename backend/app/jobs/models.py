"""The job reliability module's own table (ADR-0020): the deletions table."""

from sqlalchemy import Boolean, Text, false
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin


class ObjectDeletion(IdMixin, Base):
    """Stored objects to delete: one key, or every key under a prefix. Written in the
    transaction that removes the last reference to them; the object-deletion job and the
    sweeper delete the objects and then the row (``app.jobs.deletions``)."""

    __tablename__ = "object_deletions"

    key: Mapped[str] = mapped_column(Text)
    prefix: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
