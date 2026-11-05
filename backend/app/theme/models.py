"""The ``themes`` table: at most one row per Organisation, written on the first save."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin


class Theme(IdMixin, Base):
    __tablename__ = "themes"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"), unique=True
    )
    # {token: {"light": "#rrggbb", "dark": "#rrggbb"}} for every colour token.
    colours: Mapped[dict[str, Any]] = mapped_column(JSONB)
    radius: Mapped[int] = mapped_column(Integer)
    font: Mapped[str] = mapped_column(String(100))
    mode: Mapped[str] = mapped_column(String(20))
    launcher_type: Mapped[str] = mapped_column(String(20))
    launcher_position: Mapped[str] = mapped_column(String(20))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
