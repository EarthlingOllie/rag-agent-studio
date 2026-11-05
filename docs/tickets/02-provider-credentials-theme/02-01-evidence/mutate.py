"""Mutation proof for 02-01: apply each mutation, run the tests that should catch it, restore.

Usage: python3 mutate.py <worktree>. Each mutation must make at least one test fail; at the end
the unmodified code must pass the same tests.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
BACKEND = ["uv", "run", "pytest", "-q", "--no-cov", "-x", "-p", "no:cacheprovider",
           "tests/integration/test_provider_credentials.py",
           "tests/integration/test_no_secret_in_responses.py",
           "tests/unit/test_kms_key_wrapper.py", "tests/unit/test_http_credential_verifier.py"]
FRONTEND = ["npx", "vitest", "run", "apps/studio/src/settings/CredentialsPage.test.tsx"]

SERVICE = "backend/app/credentials/service.py"
API = "backend/app/credentials/api.py"
PAGE = "frontend/apps/studio/src/settings/CredentialsPage.tsx"
MUTATIONS = [
    ("A failed check still stores the credential", SERVICE,
     "            raise await self._check_failed(scope, None, details, result.failure)\n", ""),
    ("Rotation stores the new key despite a failed check", SERVICE,
     "            raise await self._check_failed(scope, credential.id, details, result.failure)\n",
     ""),
    ("Rotation gives the credential a new identity", SERVICE,
     "        credential.masked_suffix = _suffix(api_key)\n",
     "        credential.masked_suffix = _suffix(api_key)\n        credential.id = uuid.uuid4()\n"),
    ("Masked suffix shows 8 characters", SERVICE, "SUFFIX_LENGTH = 4", "SUFFIX_LENGTH = 8"),
    ("Re-check doesn't record a failure", SERVICE,
     "        credential.check_status = PASSED if result.passed else FAILED",
     "        credential.check_status = PASSED"),
    ("Re-check checks a key other than the stored one", SERVICE,
     "Provider(credential.provider), self._open(credential)",
     'Provider(credential.provider), "other-key"'),
    ("Delete ignores references", SERVICE, "        if references:\n", "        if False:\n"),
    ("Deletion not audited", SERVICE, '"credential.deleted"', '"credential.removed"'),
    ("Create not audited", SERVICE,
     '        await self._record(scope, "credential.created", credential_id, after=_summary(credential))\n',
     ""),
    ("Duplicate name allowed", SERVICE,
     "        if await self._name_taken(scope, new.name):\n            raise DuplicateNameError\n", ""),
    ("Unsupported capabilities accepted", SERVICE, "        if unsupported:\n", "        if False:\n"),
    ("Credentials of every Organisation listed", SERVICE,
     "            .where(ProviderCredential.organisation_id == scope.organisation_id)\n            .order_by",
     "            .order_by"),
    ("Editors can add credentials", API,
     "    body: CreateCredentialRequest, scope: OwnerScope,",
     "    body: CreateCredentialRequest, scope: Scope,"),
    ("Response carries the sealed secret", API,
     "    masked_suffix: str\n",
     '    masked_suffix: str\n    secret_sealed: str = ""\n'),
    ("Malformed key echoed back", API,
     "        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, INVALID_API_KEY)",
     "        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, INVALID_API_KEY + key)"),
    ("Failure reasons not typed", API,
     "reason=error.failure)", "reason=CheckFailure.INVALID_KEY)"),
    ("401 treated as missing model access", "backend/app/credentials/http_verifier.py",
     "    if status_code == 401:", "    if status_code == 4010:"),
    ("Network errors raise", "backend/app/credentials/http_verifier.py",
     "    except httpx.HTTPError:", "    except ValueError:"),
    ("KMS refusal leaks as ClientError", "backend/app/crypto/kms_key_wrapper.py",
     "        except (ClientError, BotoCoreError) as exc:", "        except ValueError as exc:"),
    ("KMS wrap without encryption context", "backend/app/crypto/kms_key_wrapper.py",
     "Plaintext=data_key, EncryptionContext=ENCRYPTION_CONTEXT", "Plaintext=data_key"),
    ("Owner controls shown to Editors", PAGE,
     "{isOwner && providers.data &&", "{providers.data &&"),
    ("Failure reason not shown", "frontend/apps/studio/src/settings/credentials.ts",
     "  if (reason) return `The check failed. ${FAILURE_MESSAGES[reason]}`;\n", ""),
    ("Bedrock offered in the API-key wizard", PAGE,
     'providers.filter((provider) => provider.auth_kinds.includes("api_key"))', "providers"),
    ("Delete without confirming", PAGE, '          setMode("deleting");\n', "          onDelete();\n"),
    ("References not listed on a refused delete", PAGE,
     "remove.error.references.length > 0 ? remove.error : null", "null"),
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
