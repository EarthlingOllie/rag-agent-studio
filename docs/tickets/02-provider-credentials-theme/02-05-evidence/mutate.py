"""Mutation proof for 02-05: apply each mutation, run the tests that should catch it, restore.

Usage: python3 mutate.py <worktree>. Each mutation must make at least one test fail; at the end
the unmodified code must pass the same tests.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
BACKEND = ["uv", "run", "pytest", "-q", "--no-cov", "-x", "-p", "no:randomly",
           "tests/integration/test_theme.py", "tests/integration/test_tenant_isolation.py"]
FRONTEND = ["npx", "vitest", "run", "packages/ui", "apps/studio/src/settings/ThemePage.test.tsx"]

MUTATIONS = [
    ("Editors can save the Theme", "backend/app/theme/api.py",
     "async def save_theme(body: ThemeSettings, scope: OwnerScope", "async def save_theme(body: ThemeSettings, scope: Scope"),
    ("Theme change not audited", "backend/app/theme/service.py",
     'action="theme.updated"', 'action="theme.saved"'),
    ("Audit records the whole Theme instead of what changed", "backend/app/theme/service.py",
     "        before=before,\n        after=after,", "        before=current.model_dump(mode=\"json\"),\n        after=values,"),
    ("No-op save is audited", "backend/app/theme/service.py",
     "    if not after:\n", "    if False:\n"),
    ("Organisation row not locked on save", "backend/app/theme/service.py",
     ".where(Organisation.id == scope.organisation_id).with_for_update()",
     ".where(Organisation.id == scope.organisation_id)"),
    ("Hex colours not validated", "backend/app/theme/schema.py",
     'Field(pattern=r"^#[0-9a-fA-F]{6}$", examples=["#4f46e5"])', 'Field(examples=["#4f46e5"])'),
    ("Colours not lower-cased", "backend/app/theme/schema.py",
     "    AfterValidator(str.lower),\n", ""),
    ("Radius upper bound off", "backend/app/theme/schema.py",
     "MAX_RADIUS = 24", "MAX_RADIUS = 25"),
    ("Theme read from another Organisation", "backend/app/theme/service.py",
     "select(Theme).where(Theme.organisation_id == scope.organisation_id)", "select(Theme)"),
    ("Luminance uses the wrong linear threshold", "frontend/packages/ui/src/contrast.ts",
     "channel <= 0.04045 ? channel / 12.92", "channel <= 0.5 ? channel / 12.92"),
    ("Contrast ignores the 0.05 flare term", "frontend/packages/ui/src/contrast.ts",
     "(lighter + 0.05) / (darker + 0.05)", "lighter / (darker + 0.01)"),
    ("Text pairs need only 3:1", "frontend/packages/ui/src/contrast.ts",
     'background: "surface", required: 4.5, label: "Text on surface"', 'background: "surface", required: 3, label: "Text on surface"'),
    ("Auto mode checks light only", "frontend/packages/ui/src/theme.ts",
     'mode === "auto" ? ["light", "dark"] : [mode]', 'mode === "auto" ? ["light"] : [mode]'),
    ("Resolution always takes the light value", "frontend/packages/ui/src/theme.ts",
     "theme.colours[token][scheme]", 'theme.colours[token]["light"]'),
    ("Radius resolved without a unit", "frontend/packages/ui/src/theme.ts",
     '`${String(theme.radius)}px`', "String(theme.radius)"),
    ("Contrast warnings block saving", "frontend/apps/studio/src/settings/ThemePage.tsx",
     "disabled={hasInvalid || save.isPending}", "disabled={hasInvalid || save.isPending || warnings.length > 0}"),
    ("Preview shows the saved Theme, not the draft", "frontend/apps/studio/src/settings/ThemePage.tsx",
     "<WidgetPreview theme={draft} scheme={scheme} />", "<WidgetPreview theme={saved} scheme={scheme} />"),
    ("Editors can edit the form", "frontend/apps/studio/src/settings/ThemePage.tsx",
     "<fieldset disabled={!isOwner}", "<fieldset disabled={false}"),
    ("Theme tab hidden from Editors", "frontend/apps/studio/src/settings/OrganisationSettings.tsx",
     '''        <Link to="/organisations/$organisationId/settings/theme" params={{ organisationId }} className={TAB}>
          Theme
        </Link>
        {isOwner && (''', '''        {isOwner && (
        <Link to="/organisations/$organisationId/settings/theme" params={{ organisationId }} className={TAB}>
          Theme
        </Link>)}
        {isOwner && ('''),
]


def run(command: list[str], cwd: Path) -> bool:
    return subprocess.run(command, cwd=cwd, capture_output=True, check=False).returncode == 0


caught = 0
for name, relative, old, new in MUTATIONS:
    path = ROOT / relative
    original = path.read_text()
    assert original.count(old) == 1, f"{name}: the code to mutate is not there exactly once"
    path.write_text(original.replace(old, new))
    try:
        backend = relative.startswith("backend/")
        passed = run(BACKEND, ROOT / "backend") if backend else run(FRONTEND, ROOT / "frontend")
    finally:
        path.write_text(original)
    verdict = "SURVIVED" if passed else "caught"
    caught += not passed
    print(f"{verdict:8} {name} ({relative})", flush=True)

print(f"{caught}/{len(MUTATIONS)} mutations caught", flush=True)
clean_backend = run(BACKEND, ROOT / "backend")
clean_frontend = run(FRONTEND, ROOT / "frontend")
print(f"unmodified code: backend {'passes' if clean_backend else 'FAILS'}, frontend {'passes' if clean_frontend else 'FAILS'}")
sys.exit(0 if caught == len(MUTATIONS) and clean_backend and clean_frontend else 1)
