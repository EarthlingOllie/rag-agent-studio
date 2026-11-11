"""The Audit Event table. It is append-only: migration ``0003_audit`` adds a trigger that
refuses every UPDATE and DELETE, and the audit module has no operation that changes a row."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin


class AuditEvent(IdMixin, Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_organisation_id_occurred_at", "organisation_id", "occurred_at"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    # None for events no Member caused, such as a lockout after failed sign-ins.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("members.id"))
    action: Mapped[str] = mapped_column(String(100))
    target_type: Mapped[str] = mapped_column(String(100))
    target_id: Mapped[str | None] = mapped_column(String(200))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # The time of the insert itself, not of the transaction start (``now()``), so events
    # recorded in one transaction keep their order.
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    # Increases with every insert. It breaks ties between events with the same time, such as
    # backfilled ones, so "newest first" is always the reverse order of recording.
    sequence: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
