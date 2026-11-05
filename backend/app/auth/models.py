"""Auth tables. Password reset tokens belong to a Member, so they are platform-level."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin


class PasswordResetToken(IdMixin, Base):
    """One emailed reset link. Only the token's SHA-256 is stored; it works once, until expiry."""

    __tablename__ = "password_reset_tokens"

    member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
