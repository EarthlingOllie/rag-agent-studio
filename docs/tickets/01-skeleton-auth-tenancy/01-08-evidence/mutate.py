"""Applies one mutation at a time to the 01-08 worktree, runs the tests that should catch it, restores.

Usage: python3 mutate.py <worktree>. Backend mutations run the invite, isolation and telemetry
tests; Studio mutations run the Members and accept-invite tests.
"""
import subprocess, sys
WT = sys.argv[1]
BACKEND_TESTS = ["tests/integration/test_invites.py", "tests/integration/test_tenant_isolation.py",
                 "tests/integration/test_telemetry.py"]
STUDIO_TESTS = ["apps/studio/src/settings/MembersPage.test.tsx", "apps/studio/src/invites/AcceptInvitePage.test.tsx"]
INV = "backend/app/tenancy/invites.py"
API = "backend/app/tenancy/invites_api.py"
# (name, file, old, new, which occurrence of old: 1-based)
MUTATIONS = [
    ("links are reusable (accepted invites still work)", INV,
     "        Invite.accepted_at.is_(None),\n        Invite.revoked_at.is_(None),\n        Invite.expires_at > now,",
     "        Invite.revoked_at.is_(None),\n        Invite.expires_at > now,", 1),
    ("links never expire", INV, "        Invite.expires_at > now,\n", "", 1),
    ("revoked links still work", INV,
     "        Invite.revoked_at.is_(None),\n        Invite.expires_at > now,", "        Invite.expires_at > now,", 1),
    ("tokens stored in plain text", INV, "return hashlib.sha256(token.encode()).hexdigest()", "return token", 1),
    ("renewing keeps the old link working", INV, "token, invite.token_hash = _new_token()", "token, _unused = _new_token()", 1),
    ("an invite for another email can be accepted", INV, "    if invite.email != member.email:", "    if False:", 1),
    ("accepting adds no membership", INV,
     "    session.add(\n        Membership(organisation_id=invite.organisation_id, member_id=member.id, role=invite.role)\n    )",
     "    pass", 1),
    ("accepting ignores the invited role", INV,
     "member_id=member.id, role=invite.role)", "member_id=member.id, role=Role.EDITOR)", 1),
    ("existing Members can be invited again", INV, "    if already_member is not None:\n        raise AlreadyAMemberError", "    if False:\n        raise AlreadyAMemberError", 1),
    ("invite.created not recorded", INV, 'action="invite.created"', 'action="invite.other"', 1),
    ("invite.revoked not recorded", INV, 'action="invite.revoked"', 'action="invite.other"', 1),
    ("invite.accepted not recorded", INV, 'action="invite.accepted"', 'action="invite.other"', 1),
    ("revoked invites stay in the pending list", INV,
     "            Invite.accepted_at.is_(None),\n            Invite.revoked_at.is_(None),\n        )\n        .order_by",
     "            Invite.accepted_at.is_(None),\n        )\n        .order_by", 1),
    ("revoking another Organisation's invite", INV,
     "            Invite.id == invite_id,\n            Invite.organisation_id == scope.organisation_id,",
     "            Invite.id == invite_id,", 1),
    ("Editors can manage invites", API, "from app.tenancy.policy import NOT_FOUND, OWNERS_ONLY, OwnerScope",
     "from app.tenancy.policy import NOT_FOUND, OWNERS_ONLY\nfrom app.tenancy.policy import Scope as OwnerScope", 1),
    ("accepting doesn't rotate the session", API,
     "    await start_session(response, request, sessions, member, token)", "    await start_session(response, request, sessions, member, None)", 1),
    ("a failed invite email loses the link (500)", API, "        except Exception:\n            logger.exception", "        except ZeroDivisionError:\n            logger.exception", 1),
    ("link tokens exported in telemetry", "backend/app/core/telemetry.py",
     "extra_patterns=(*MESSAGE_PATTERNS, *TOKEN_PATTERNS)", "extra_patterns=MESSAGE_PATTERNS", 1),
    ("Studio: Members tab shown to Editors", "frontend/apps/studio/src/settings/MembersPage.tsx",
     "  if (!isOwner) return", "  if (isOwner && !isOwner) return", 1),
    ("Studio: no copyable link after inviting", "frontend/apps/studio/src/settings/MembersPage.tsx",
     "      {issued && <InviteLink", "      {issued && false && <InviteLink", 1),
    ("Studio: invite sent without the chosen role", "frontend/apps/studio/src/settings/MembersPage.tsx",
     "role: data.get(\"role\") as Role", "role: \"editor\"", 1),
    ("Studio: pending invites not listed", "frontend/apps/studio/src/settings/MembersPage.tsx",
     "        {invites.data.map((invite) => (", "        {invites.data.slice(0, 0).map((invite) => (", 1),
    ("Studio: accept page offers Join to the wrong account", "frontend/apps/studio/src/invites/AcceptInvitePage.tsx",
     "session.member.email === invite.email", "session.member.email !== \"\"", 1),
    ("Studio: existing account offered sign-up instead of sign-in", "frontend/apps/studio/src/invites/AcceptInvitePage.tsx",
     "invite.account_exists ?", "false ?", 1),
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
