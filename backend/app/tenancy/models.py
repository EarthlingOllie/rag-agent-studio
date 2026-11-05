"""Tenancy tables.

``organisations`` and ``members`` are platform-level: a Member can belong to several
Organisations. Every table below the platform level carries an ``organisation_id`` and is
read only through repository functions that take an ``OrganisationScope``.
"""

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin

# The MFA tables belong to the Member, so they sit at the platform level with ``members``.
PLATFORM_TABLES = frozenset({"organisations", "members", "mfa_factors", "mfa_recovery_codes"})


class Role(enum.StrEnum):
    OWNER = "owner"
    EDITOR = "editor"


class Organisation(IdMixin, Base):
    __tablename__ = "organisations"

    name: Mapped[str] = mapped_column(String(200))


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
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="role", values_callable=lambda roles: [r.value for r in roles])
    )
