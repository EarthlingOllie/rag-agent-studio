"""Loading the repo's price table into ``model_prices``, run by every ``alembic upgrade``."""

from collections.abc import Sequence

from sqlalchemy import delete, insert, inspect
from sqlalchemy.engine import Connection

from app.pricing.models import ModelPrice
from app.pricing.table import PriceEntry, load_price_file


def sync_price_table(connection: Connection, entries: Sequence[PriceEntry] | None = None) -> bool:
    """Makes ``model_prices`` hold exactly ``entries`` (by default, the repo's price file), in
    the caller's transaction. Does nothing, and answers False, while the table doesn't exist
    (migrating down to before it)."""
    if not inspect(connection).has_table(ModelPrice.__tablename__):
        return False
    rows = load_price_file() if entries is None else entries
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
    return True
