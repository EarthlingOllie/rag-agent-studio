"""Tenancy tables.

``organisations`` and ``members`` are platform-level: a Member can belong to several
Organisations. Every table below the platform level carries an ``organisation_id`` and is
read only through repository functions that take an ``OrganisationScope``.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin

# Tables that belong to no single Organisation: Organisations themselves, Members (who can
# belong to several), per-Member auth state such as password reset tokens and MFA, and the
# platform price table.
PLATFORM_TABLES = frozenset(
    {
        "organisations",
        "members",
        "password_reset_tokens",
        "mfa_factors",
        "mfa_recovery_codes",
        "model_prices",
    }
)


DEFAULT_RETENTION_DAYS = 90


class Role(enum.StrEnum):
    OWNER = "owner"
    EDITOR = "editor"


def _role_type() -> Enum:
    return Enum(Role, name="role", values_callable=lambda roles: [r.value for r in roles])


class Organisation(IdMixin, Base):
    __tablename__ = "organisations"

    name: Mapped[str] = mapped_column(String(200))
    # The Require MFA policy: while it is on, Members without MFA are refused this
    # Organisation's routes until they enrol (``app.tenancy.policy``).
    require_mfa: Mapped[bool] = mapped_column(Boolean, server_default=false(), default=False)
    # The Retention Window: Message text and feedback comments older than this many days are
    # purged daily (``app.retention``); metrics are kept.
    retention_days: Mapped[int] = mapped_column(
        Integer, server_default=text("90"), default=DEFAULT_RETENTION_DAYS
    )


class Member(IdMixin, Base):
    __tablename__ = "members"

    name: Mapped[str] = mapped_column(String(200))
    # Stored normalised (trimmed, lower case), so the unique constraint is case-insensitive.
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))


class Membership(IdMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("organisation_id", "member_id"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[Role] = mapped_column(_role_type())


class Invite(IdMixin, Base):
    """An invitation to join an Organisation with a role, addressed to one email.

    Only the SHA-256 of the link's token is stored. An Invite is pending until it is accepted
    or revoked, and its link works only while it is pending and before ``expires_at``.
    """

    __tablename__ = "invites"
    __table_args__ = (
        # One pending Invite per email in an Organisation.
        Index(
            "uq_invites_pending_email",
            "organisation_id",
            "email",
            unique=True,
            postgresql_where=text("accepted_at IS NULL AND revoked_at IS NULL"),
        ),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    # Normalised like ``members.email``.
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[Role] = mapped_column(_role_type())
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    invited_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("members.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("members.id", ondelete="SET NULL")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
