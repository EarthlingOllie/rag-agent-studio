"""Mutation proof for ticket 01-12: each mutation breaks one behaviour; the named tests must fail.

Run from the repository root: python3 mutate.py. Each file is restored after its mutation.
Backend tests use TEST_DATABASE_URL / TEST_REDIS_URL from the environment.
"""

import subprocess
import sys
from pathlib import Path

BACKEND_TESTS = "tests/integration/test_require_mfa.py"
FRONTEND_TESTS = "apps/studio/src/security/RequireMfa.test.tsx"

MUTATIONS = [
    ("policy: Members without MFA are let in", "backend/app/tenancy/policy.py",
     "if require_mfa and not await mfa_enabled(db, member.id):", "if False:",
     "backend", "test_members_without_mfa_are_refused_every_organisation_route"),
    ("policy: MFA checked only on Owner-only routes", "backend/app/tenancy/policy.py",
     "if require_mfa and not await mfa_enabled(db, member.id):",
     "if require_mfa and self.role is Role.OWNER and not await mfa_enabled(db, member.id):",
     "backend", "test_the_api_lets_a_member_in_once_they_enrol"),
    ("an Owner without MFA may require it", "backend/app/tenancy/mfa_policy.py",
     "if require_mfa and not await mfa_enabled(session, scope.member_id):", "if False:",
     "backend", "test_an_owner_without_mfa_cannot_require_it"),
    ("policy change not audited", "backend/app/tenancy/mfa_policy.py",
     "    await audit.record(", "    0 and await audit.record(",
     "backend", "test_policy_changes_are_audit_events"),
    ("a no-op change is audited", "backend/app/tenancy/mfa_policy.py",
     "if organisation.require_mfa is require_mfa:", "if False:",
     "backend", "test_policy_changes_are_audit_events"),
    ("MFA can be disabled while required", "backend/app/auth/mfa.py",
     "        if names:\n            raise MfaRequiredByOrganisationError(names)", "",
     "backend", "test_a_member_cannot_disable_mfa_while_an_organisation_requires_it"),
    ("only the first requiring Organisation named", "backend/app/auth/mfa.py",
     "names = list(requiring)", "names = list(requiring)[:1]",
     "backend", "test_every_requiring_organisation_is_named_when_disabling_is_refused"),
    ("/me never reports MFA", "backend/app/auth/api.py",
     "mfa_enabled=await mfa_enabled(db, member.id),", "mfa_enabled=False,",
     "backend", "test_me_says_whether_the_member_has_mfa"),
    ("/me never reports the policy", "backend/app/auth/api.py",
     "mfa_required=m.require_mfa,", "mfa_required=False,",
     "backend", "test_owners_turn_the_policy_on_and_off_in_organisation_settings"),
    ("Studio: no redirect to enrolment", "frontend/apps/studio/src/shell/SignedInShell.tsx",
     "{mustEnrol && !onSecurityPage ? (", "{false ? (",
     "frontend", "every page of the Organisation leads to enrolment"),
    ("Studio: navigation not limited while enrolment is due", "frontend/apps/studio/src/shell/SignedInShell.tsx",
     "{!mustEnrol && (", "{true && (",
     "frontend", "guided through enrolment first"),
    ("Studio: session not refreshed after enrolling", "frontend/apps/studio/src/security/mfa.ts",
     "        queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY }),\n", "",
     "frontend", "guided through enrolment first"),
    ("Studio: session not refreshed after a policy change", "frontend/apps/studio/src/settings/mfaPolicy.ts",
     "onSuccess: () => queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY }),", "",
     "frontend", "an Owner requires MFA in Organisation settings"),
    ("Studio: the API's refusal message is dropped", "frontend/apps/studio/src/security/SecurityPage.tsx",
     "return typeof detail === \"string\" ? detail :", "return typeof detail === \"number\" ? detail :",
     "frontend", "can't turn MFA off while an Organisation requires it"),
    ("Studio: Editors get the policy button", "frontend/apps/studio/src/settings/OrganisationSettings.tsx",
     "{isOwner ? (", "{true ? (",
     "frontend", "Editors see the policy but can't change it"),
]


def run(kind: str, name: str) -> int:
    if kind == "backend":
        command = ["uv", "run", "pytest", "-q", "--no-cov", "-x", BACKEND_TESTS, "-k", name]
        cwd = "backend"
    else:
        command = ["pnpm", "exec", "vitest", "run", FRONTEND_TESTS, "-t", name]
        cwd = "frontend"
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True).returncode


# Every named test must pass on the unmodified code first, so a failure below is the mutation's.
for _, _, _, _, kind, test in MUTATIONS:
    assert run(kind, test) == 0, f"{kind} test {test!r} fails on the unmodified code"
print("every named test passes on the unmodified code", flush=True)

caught = 0
for title, path, old, new, kind, test in MUTATIONS:
    file = Path(path)
    original = file.read_text()
    assert original.count(old) == 1, (title, old)
    file.write_text(original.replace(old, new))
    try:
        code = run(kind, test)
    finally:
        file.write_text(original)
    verdict = "CAUGHT" if code != 0 else "SURVIVED"
    caught += code != 0
    print(f"{verdict}: {title}  [{kind}: {test}]", flush=True)

print(f"{caught}/{len(MUTATIONS)} mutations caught")
backend = run("backend", "")
frontend = run("frontend", "")
print(f"unmodified code: backend tests exit {backend}, Studio tests exit {frontend}")
sys.exit(0 if caught == len(MUTATIONS) and backend == frontend == 0 else 1)
