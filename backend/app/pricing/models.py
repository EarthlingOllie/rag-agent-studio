"""The ``model_prices`` and ``price_overrides`` tables.

``model_prices`` is platform-level: the repo's price table, reloaded on every migrate.
``price_overrides`` holds an Owner's prices for one model of one credential; a price left
null keeps the platform's. Overrides go with their credential when it is deleted.

``voice_prices`` is platform-level too: the voice layer's price per Call minute by provider,
reloaded with the price table. ``voice_price_overrides`` holds an Owner's per-minute price for
one voice credential.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin

# Dollars per million tokens, to a millionth of a dollar.
PRICE = Numeric(12, 6)


class ModelPrice(IdMixin, Base):
    __tablename__ = "model_prices"
    __table_args__ = (UniqueConstraint("provider", "model", "effective_from"),)

    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(200))
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    input: Mapped[Decimal] = mapped_column(PRICE)
    output: Mapped[Decimal] = mapped_column(PRICE)
    cached_input: Mapped[Decimal] = mapped_column(PRICE)


class PriceOverride(IdMixin, Base):
    __tablename__ = "price_overrides"
    __table_args__ = (UniqueConstraint("credential_id", "model"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    credential_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("provider_credentials.id", ondelete="CASCADE")
    )
    model: Mapped[str] = mapped_column(String(200))
    input: Mapped[Decimal | None] = mapped_column(PRICE)
    output: Mapped[Decimal | None] = mapped_column(PRICE)
    cached_input: Mapped[Decimal | None] = mapped_column(PRICE)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


# Dollars per Call minute, to a millionth of a dollar.
PER_MINUTE = Numeric(12, 6)


class VoicePrice(IdMixin, Base):
    __tablename__ = "voice_prices"
    __table_args__ = (UniqueConstraint("provider", "effective_from"),)

    provider: Mapped[str] = mapped_column(String(32))
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    per_minute: Mapped[Decimal] = mapped_column(PER_MINUTE)


class VoicePriceOverride(IdMixin, Base):
    __tablename__ = "voice_price_overrides"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    credential_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("provider_credentials.id", ondelete="CASCADE"), unique=True
    )
    per_minute: Mapped[Decimal] = mapped_column(PER_MINUTE)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
