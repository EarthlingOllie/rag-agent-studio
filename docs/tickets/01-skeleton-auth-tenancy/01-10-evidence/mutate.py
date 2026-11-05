"""Applies one mutation at a time to the 01-10 worktree, runs the tests that should catch it, restores.

Usage: python3 mutate.py <worktree>. Backend mutations run the switcher, isolation, sign-in and
invite tests; Studio mutations run the shell, switcher, Members and accept-invite tests.
"""
import subprocess, sys
WT = sys.argv[1]
BACKEND_TESTS = ["tests/integration/test_organisation_switcher.py", "tests/integration/test_tenant_isolation.py",
                 "tests/integration/test_sign_in_and_out.py", "tests/integration/test_invites.py"]
STUDIO_TESTS = ["apps/studio/src/shell", "apps/studio/src/settings/MembersPage.test.tsx",
                "apps/studio/src/invites/AcceptInvitePage.test.tsx"]
ACTIVE = "backend/app/tenancy/active.py"
SWITCH = "backend/app/tenancy/switcher_api.py"
INV = "backend/app/tenancy/invites.py"
SWITCHER = "frontend/apps/studio/src/shell/OrganisationSwitcher.tsx"
SHELL = "frontend/apps/studio/src/shell/SignedInShell.tsx"
# (name, file, old, new, which occurrence of old: 1-based)
MUTATIONS = [
    ("switching to an Organisation the Member doesn't belong to is allowed", SWITCH,
     "    if scope is None:\n        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)\n    await ActiveOrganisations(request.app.state.redis).remember(member.id, scope.organisation_id)",
     "    await ActiveOrganisations(request.app.state.redis).remember(member.id, body.organisation_id)", 1),
    ("the choice is not remembered", SWITCH,
     "    await ActiveOrganisations(request.app.state.redis).remember(member.id, scope.organisation_id)\n", "", 1),
    ("a remembered Organisation the Member left stays active", ACTIVE,
     "        if remembered in memberships:", "        if remembered is not None:", 1),
    ("the active Organisation is always the first", ACTIVE,
     "        if remembered in memberships:", "        if False:", 1),
    ("one choice shared by every Member", ACTIVE, 'return f"{_KEY_PREFIX}{member_id}"', 'return _KEY_PREFIX', 1),
    ("/me doesn't report the active Organisation", "backend/app/auth/api.py",
     "        active_organisation_id=active,", "        active_organisation_id=None,", 1),
    ("an Organisation's invite reachable through the Member's other Organisation", INV,
     "            Invite.id == invite_id,\n            Invite.organisation_id == scope.organisation_id,",
     "            Invite.id == invite_id,", 1),
    ("the invite list shows every Organisation the Member belongs to", INV,
     "            Invite.organisation_id == scope.organisation_id,\n            Invite.accepted_at.is_(None),",
     "            Invite.organisation_id.in_(\n                select(Membership.organisation_id).where(Membership.member_id == scope.member_id)\n            ),\n            Invite.accepted_at.is_(None),", 1),
    ("Studio: no switcher for Members of two Organisations", SWITCHER,
     "session.organisations.length < 2", "session.organisations.length < 3", 1),
    ("Studio: `/` ignores the remembered Organisation", SHELL,
     "const active = (data as Session).active_organisation_id;",
     "const active = (data as Session).organisations[0]?.id ?? null;", 1),
    ("Studio: switching doesn't open the chosen Organisation", SWITCHER,
     "              void navigate({", "              if (Math.random() > 2) void navigate({", 1),
    ("Studio: switching isn't sent to the API", "frontend/apps/studio/src/auth/session.ts",
     "body: { organisation_id: organisationId }", "body: { organisation_id: \"\" }", 1),
    ("Studio: invites cached across Organisations", "frontend/apps/studio/src/invites/invites.ts",
     '["invites", organisationId] as const', '["invites"] as const', 1),
    ("Studio: a failed switch isn't reported", SWITCHER,
     "      {switchOrganisation.isError && (", "      {false && (", 1),
]


def replace_nth(src: str, old: str, new: str, n: int) -> str:
    index = -1
    for _ in range(n):
        index = src.index(old, index + 1)
    return src[:index] + new + src[index + len(old):]


def run(frontend: bool) -> subprocess.CompletedProcess[str]:
    if frontend:
        return subprocess.run(["npx", "vitest", "run", *STUDIO_TESTS], cwd=f"{WT}/frontend", capture_output=True, text=True)
    return subprocess.run(["uv", "run", "pytest", "-q", "--no-cov", "-p", "no:cacheprovider", *BACKEND_TESTS],
                          cwd=f"{WT}/backend", capture_output=True, text=True)


caught = 0
for name, path, old, new, n in MUTATIONS:
    full = f"{WT}/{path}"
    src = open(full).read()
    assert old in src, (name, old)
    open(full, "w").write(replace_nth(src, old, new, n))
    try:
        r = run(path.startswith("frontend/"))
    finally:
        open(full, "w").write(src)
    out = r.stdout + r.stderr
    if path.startswith("frontend/"):
        failed = sorted({l.strip()[2:].split(" > ")[-1].split("  ")[0] for l in out.splitlines() if l.strip().startswith("× ")})
    else:
        failed = [l.split(" - ")[0].replace("FAILED ", "").split("::")[-1] for l in out.splitlines() if l.startswith("FAILED")]
    status = "CAUGHT" if r.returncode != 0 else "SURVIVED"
    caught += r.returncode != 0
    print(f"== mutation: {name}  ({path})\n   {status}; failing tests:")
    for f in failed:
        print(f"     {f}")
print(f"\n{caught}/{len(MUTATIONS)} mutations caught")
print("unmodified backend:", run(False).stdout.strip().splitlines()[-1])
print("unmodified studio:", [l.strip() for l in run(True).stdout.splitlines() if "Tests" in l][-1])
