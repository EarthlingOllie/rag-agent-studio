"""Loading the repo's price table into ``model_prices`` and ``voice_prices``, run by every
``alembic upgrade``."""

from collections.abc import Sequence

from sqlalchemy import delete, insert, inspect
from sqlalchemy.engine import Connection

from app.pricing.models import ModelPrice, VoicePrice
from app.pricing.table import (
    PriceEntry,
    VoicePriceEntry,
    load_price_file,
    load_voice_price_file,
)


def sync_price_table(
    connection: Connection,
    entries: Sequence[PriceEntry] | None = None,
    voice_entries: Sequence[VoicePriceEntry] | None = None,
) -> bool:
    """Makes ``model_prices`` hold exactly ``entries`` and ``voice_prices`` exactly
    ``voice_entries`` (by default, the repo's price file), in the caller's transaction. Does
    nothing, and answers False, while the model table doesn't exist (migrating down to before
    it); the voice table is left alone while it doesn't exist."""
    tables = inspect(connection)
    if not tables.has_table(ModelPrice.__tablename__):
        return False
    rows = load_price_file() if entries is None else entries
    voice_rows = load_voice_price_file() if voice_entries is None else voice_entries
    connection.execute(delete(ModelPrice))
    if rows:
        connection.execute(
            insert(ModelPrice),
            [
                {
                    "provider": str(entry.provider),
                    "model": entry.model,
                    "effective_from": entry.effective_from,
                    "input": entry.input,
                    "output": entry.output,
                    "cached_input": entry.cached_input,
                }
                for entry in rows
            ],
        )
    if tables.has_table(VoicePrice.__tablename__):
        connection.execute(delete(VoicePrice))
        if voice_rows:
            connection.execute(
                insert(VoicePrice),
                [
                    {
                        "provider": str(entry.provider),
                        "effective_from": entry.effective_from,
                        "per_minute": entry.per_minute,
                    }
                    for entry in voice_rows
                ],
            )
    return True
