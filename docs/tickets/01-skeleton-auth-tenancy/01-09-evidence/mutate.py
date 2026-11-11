"""Mutation proof for 01-09: apply each mutation, run the tests that should catch it, restore.

Usage: python3 mutate.py <worktree>. Each mutation must make at least one test fail; at the end
the unmodified code must pass the same tests.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
BACKEND = ["uv", "run", "pytest", "-q", "--no-cov", "-x",
           "tests/integration/test_members.py", "tests/integration/test_tenant_isolation.py"]
FRONTEND = ["npx", "vitest", "run", "apps/studio/src/settings"]

MUTATIONS = [
    ("Editors pass the Owner-only policy", "backend/app/tenancy/policy.py",
     "if _RANK[scope.role] < _RANK[self.role]:", "if False:"),
    ("Owner-only policy refuses with 404 instead of 403", "backend/app/tenancy/policy.py",
     "raise HTTPException(status.HTTP_403_FORBIDDEN, OWNERS_ONLY)",
     "raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)"),
    ("No last-Owner check", "backend/app/tenancy/members.py",
     "    if membership.role is not Role.OWNER:\n        return\n",
     "    return\n"),
    ("Last-Owner count off by one", "backend/app/tenancy/members.py",
     "if owners == 1:", "if owners == 0:"),
    ("Organisation row not locked", "backend/app/tenancy/members.py",
     ".where(Organisation.id == scope.organisation_id).with_for_update()",
     ".where(Organisation.id == scope.organisation_id)"),
    ("Demotion skips the last-Owner check", "backend/app/tenancy/members.py",
     "if role is not Role.OWNER:", "if False:"),
    ("Removal keeps the membership", "backend/app/tenancy/members.py",
     "await session.delete(membership)", "pass"),
    ("Role change not recorded", "backend/app/tenancy/members.py",
     'action="member.role_changed"', 'action="member.updated"'),
    ("Removal recorded as leaving", "backend/app/tenancy/members.py",
     'action="member.removed"', 'action="member.left"'),
    ("Members list open to Editors", "backend/app/tenancy/members_api.py",
     "async def list_members(scope: OwnerScope", "async def list_members(scope: Scope"),
    ("Leaving needs an Owner", "backend/app/tenancy/members_api.py",
     "async def leave_organisation(scope: Scope", "async def leave_organisation(scope: OwnerScope"),
    ("Members tab shown to Editors", "frontend/apps/studio/src/settings/OrganisationSettings.tsx",
     "{isOwner && (", "{(isOwner || true) && ("),
    ("Role change doesn't refresh the session", "frontend/apps/studio/src/settings/members.ts",
     "      queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY }),\n", ""),
    ("Last-Owner refusal shown as a generic error", "frontend/apps/studio/src/settings/members.ts",
     "error.status === 409 && error.detail", "error.status === 999 && error.detail"),
    ("Remove offered on your own row", "frontend/apps/studio/src/settings/MembersList.tsx",
     "{!isYou &&", "{(!isYou || true) &&"),
    ("Remove without confirming", "frontend/apps/studio/src/settings/MembersList.tsx",
     "                setConfirming(true);\n", "                onRemove();\n"),
]


def run(command: list[str], cwd: Path) -> bool:
    return subprocess.run(command, cwd=cwd, capture_output=True).returncode == 0


failures = 0
for name, file, old, new in MUTATIONS:
    path = ROOT / file
    original = path.read_text()
    assert original.count(old) == 1, (name, old)
    path.write_text(original.replace(old, new))
    try:
        backend = file.startswith("backend/")
        passed = run(BACKEND, ROOT / "backend") if backend else run(FRONTEND, ROOT / "frontend")
    finally:
        path.write_text(original)
    print(f"{'SURVIVED' if passed else 'caught  '}  {name}  ({file})", flush=True)
    failures += passed

clean = run(BACKEND, ROOT / "backend") and run(FRONTEND, ROOT / "frontend")
print(f"unmodified code passes: {clean}")
print(f"{len(MUTATIONS) - failures}/{len(MUTATIONS)} mutations caught")
sys.exit(0 if failures == 0 and clean else 1)
