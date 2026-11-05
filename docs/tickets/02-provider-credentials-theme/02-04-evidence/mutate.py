"""Mutation proof for ticket 02-04: each mutation breaks one acceptance behaviour on purpose,
and the tests that cover it must fail. Then the unmodified code must pass.

Usage: python mutate.py <repo root>   (needs TEST_DATABASE_URL / TEST_REDIS_URL for backend tests)
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
BACKEND = ["uv", "run", "pytest", "--no-cov", "-q", "-x", "-p", "no:cacheprovider"]
COST_TESTS = [*BACKEND, "tests/unit/test_cost.py"]
PRICE_TESTS = [*BACKEND, "tests/integration/test_prices.py"]
STUDIO_TESTS = ["pnpm", "vitest", "run", "apps/studio/src/settings/PriceTable.test.tsx"]

MUTATIONS = [
    (
        "the cost ignores overrides",
        "backend/app/pricing/table.py",
        "        if overridden is not None:\n            return overridden",
        "        if False:\n            return overridden",
        COST_TESTS,
    ),
    (
        "the cost uses the earliest price, not the one in effect",
        "backend/app/pricing/table.py",
        "    return max(started, key=lambda entry: entry.effective_from, default=None)",
        "    return min(started, key=lambda entry: entry.effective_from, default=None)",
        COST_TESTS,
    ),
    (
        "the cost uses prices that take effect later",
        "backend/app/pricing/table.py",
        "and entry.effective_from <= at",
        "and entry.effective_from <= at.replace(year=9999)",
        COST_TESTS,
    ),
    (
        "the cost ignores the provider",
        "backend/app/pricing/table.py",
        "if entry.provider == provider and entry.model == model",
        "if entry.model == model",
        COST_TESTS,
    ),
    (
        "migrating does not load the price table",
        "backend/migrations/env.py",
        "        sync_price_table(connection)\n",
        "",
        PRICE_TESTS,
    ),
    (
        "a malformed price file is loaded anyway",
        "backend/app/pricing/table.py",
        "        if key in seen:\n            raise PriceFileError",
        "        if False:\n            raise PriceFileError",
        PRICE_TESTS,
    ),
    (
        "Editors may override prices",
        "backend/app/pricing/api.py",
        "    scope: OwnerScope,\n    db: Db,",
        "    scope: Scope,\n    db: Db,",
        PRICE_TESTS,
    ),
    (
        "overrides are not audited",
        "backend/app/pricing/service.py",
        "            action=OVERRIDDEN,",
        '            action="credential.something_else",',
        PRICE_TESTS,
    ),
    (
        "any model can be overridden",
        "backend/app/pricing/service.py",
        "    if model not in {offered.id for offered, _ in _offered(credential)}:",
        "    if False:",
        PRICE_TESTS,
    ),
    (
        "the Studio hides that a price is overridden",
        "frontend/apps/studio/src/settings/PriceTable.tsx",
        "      {overridden && (",
        "      {false && (",
        STUDIO_TESTS,
    ),
    (
        "the Studio sends a blank price as zero",
        "frontend/apps/studio/src/settings/prices.ts",
        '  if (trimmed === "") return null;',
        '  if (trimmed === "") return "0";',
        STUDIO_TESTS,
    ),
]


def run(command: list[str]) -> int:
    cwd = ROOT / ("frontend" if command[0] == "pnpm" else "backend")
    return subprocess.run(command, cwd=cwd, capture_output=True, check=False).returncode


caught = 0
for name, file, old, new, command in MUTATIONS:
    path = ROOT / file
    original = path.read_text()
    assert original.count(old) == 1, f"{file}: mutation anchor not found once: {old!r}"
    path.write_text(original.replace(old, new))
    try:
        code = run(command)
    finally:
        path.write_text(original)
    verdict = "CAUGHT" if code != 0 else "SURVIVED"
    caught += code != 0
    print(f"{verdict}: {name} ({file})", flush=True)

print(f"{caught}/{len(MUTATIONS)} mutations caught")
clean = [run(COST_TESTS), run(PRICE_TESTS), run(STUDIO_TESTS)]
print(f"unmodified code: {'passes' if clean == [0, 0, 0] else f'FAILS {clean}'}")
sys.exit(0 if caught == len(MUTATIONS) and clean == [0, 0, 0] else 1)
