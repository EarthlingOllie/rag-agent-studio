"""``python -m app.seed [--reset] [--assets DIR]``: the command behind ``make seed`` and
``make seed-reset``. It runs the API in process, so it needs the same settings as the API, and
prints the demo sign-in details when done."""

import argparse
import asyncio
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from app.main import create_app
from app.seed.runner import SeedError, SeedReport, real_credential_from_env, reset, seed

# The repository's ``seed`` folder; in the API image it is mounted at /seed.
DEFAULT_ASSETS = Path(__file__).resolve().parents[3] / "seed"


async def _run(assets: Path, *, wipe: bool) -> SeedReport:
    real = real_credential_from_env(os.environ)
    app = create_app()
    async with app.router.lifespan_context(app):
        return await (reset if wipe else seed)(app, assets, real)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.seed", description=__doc__)
    parser.add_argument("--reset", action="store_true", help="erase the demo Organisation first")
    parser.add_argument("--assets", type=Path, default=DEFAULT_ASSETS, help="the seed folder")
    args = parser.parse_args(argv)
    try:
        report = asyncio.run(_run(args.assets, wipe=args.reset))
    except SeedError as error:
        print(f"Seed failed: {error}", file=sys.stderr)
        return 1
    print("\n".join(report.lines()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
