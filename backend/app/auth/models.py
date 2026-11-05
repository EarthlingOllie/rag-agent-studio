"""MFA tables. Like ``members``, they are platform-level: MFA belongs to the Member, not to
one of their Organisations."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, LargeBinary, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin


class MfaFactor(Base):
    """A Member's TOTP authenticator. Unconfirmed (``confirmed_at`` null) during enrolment."""

    __tablename__ = "mfa_factors"

    member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), primary_key=True
    )
    # The base32 TOTP secret, envelope-encrypted (``app.crypto.envelope``).
    secret_sealed: Mapped[bytes] = mapped_column(LargeBinary)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The last 30-second step a code was accepted for; older and equal steps are refused.
    last_used_step: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecoveryCode(IdMixin, Base):
    __tablename__ = "mfa_recovery_codes"
    __table_args__ = (UniqueConstraint("member_id", "code_hash"),)

    member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), index=True
    )
    # SHA-256 (hex) of the normalised code. Codes carry 80 random bits, so a fast hash suffices.
    code_hash: Mapped[str] = mapped_column(String(64))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
