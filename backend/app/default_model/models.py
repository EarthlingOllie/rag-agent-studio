"""The ``default_models`` table: at most one row per Organisation, written when first set.

The credential it uses is registered with the credentials module as a reference, so the
credential can't be deleted while it is the Default Model's. The foreign key backs that up.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin


class DefaultModel(IdMixin, Base):
    __tablename__ = "default_models"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), unique=True
    )
    credential_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("provider_credentials.id"), index=True
    )
    model: Mapped[str] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
