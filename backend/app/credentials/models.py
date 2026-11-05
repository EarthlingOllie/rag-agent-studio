"""The Provider Credential table.

The secret is stored only sealed (``app.crypto.envelope``), bound to the credential's ID and
Organisation, so a sealed value copied onto another row fails to open. Provider, auth kind,
capabilities and check outcome are plain strings, so new providers need no enum migration.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin


class ProviderCredential(IdMixin, Base):
    __tablename__ = "provider_credentials"
    __table_args__ = (UniqueConstraint("organisation_id", "name"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(32))
    auth_kind: Mapped[str] = mapped_column(String(32))
    secret_sealed: Mapped[bytes] = mapped_column(LargeBinary)
    # Only for providers that have regions (Bedrock, ticket 02-02).
    region: Mapped[str | None] = mapped_column(String(32))
    # The last characters of the secret, which is all the API ever shows of it.
    masked_suffix: Mapped[str] = mapped_column(String(8))
    capabilities: Mapped[list[str]] = mapped_column(ARRAY(String(32)))
    # "passed" or "failed", with the typed reason when it failed.
    check_status: Mapped[str] = mapped_column(String(16))
    check_failure: Mapped[str | None] = mapped_column(String(32))
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # When the secret was last set: at creation, then at each rotation.
    secret_set_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
