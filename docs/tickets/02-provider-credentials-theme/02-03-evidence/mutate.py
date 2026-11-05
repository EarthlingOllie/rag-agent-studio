"""Mutation proof for ticket 02-03: each mutation breaks one acceptance behaviour on purpose,
and the tests that cover it must fail. Then the unmodified code must pass.

Usage: python mutate.py <repo root>   (needs TEST_DATABASE_URL / TEST_REDIS_URL for backend tests)
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
BACKEND = ["uv", "run", "pytest", "--no-cov", "-q", "-x", "-p", "no:cacheprovider"]
GATEWAY_TESTS = [*BACKEND, "tests/unit/test_model_gateway.py"]
DEFAULT_TESTS = [*BACKEND, "tests/integration/test_default_model.py"]
STUDIO_TESTS = ["pnpm", "vitest", "run", "apps/studio/src/settings/ModelsPage.test.tsx"]

MUTATIONS = [
    (
        "gateway builds a model for a capability the credential wasn't given",
        "backend/app/gateway/gateway.py",
        "    if capability not in credential.capabilities:",
        "    if False:",
        GATEWAY_TESTS,
    ),
    (
        "gateway builds a model its provider doesn't offer for the capability",
        "backend/app/gateway/gateway.py",
        "    if model not in {m.id",
        "    if False and model not in {m.id",
        GATEWAY_TESTS,
    ),
    (
        "fake adapters ignore the chat model a test injects",
        "backend/app/gateway/fakes.py",
        "        return self._chat(provider, secret, model)",
        "        return fake_chat(provider, secret, model)",
        GATEWAY_TESTS,
    ),
    (
        "live OpenAI chat model is built without the credential's key",
        "backend/app/gateway/live.py",
        "        return OpenAIProvider(api_key=secret, http_client=self._client)",
        '        return OpenAIProvider(api_key="sk-not-the-stored-key", http_client=self._client)',
        GATEWAY_TESTS,
    ),
    (
        "model list ignores the capabilities the credential was given",
        "backend/app/credentials/registry.py",
        "    if capability not in capabilities:\n        return ()",
        "    if False:\n        return ()",
        DEFAULT_TESTS,
    ),
    (
        "Default Model is not registered as a credential reference",
        "backend/app/main.py",
        "    app.state.credential_references.register(default_model_references)\n",
        "",
        DEFAULT_TESTS,
    ),
    (
        "Editors may set the Default Model",
        "backend/app/default_model/api.py",
        "    scope: OwnerScope,\n    db: Db,\n    clock",
        "    scope: Scope,\n    db: Db,\n    clock",
        DEFAULT_TESTS,
    ),
    (
        "changing the Default Model is not audited",
        "backend/app/default_model/service.py",
        "        action=CHANGED,",
        '        action="default_model.something_else",',
        DEFAULT_TESTS,
    ),
    (
        "the Studio picker offers credentials without chat",
        "frontend/apps/studio/src/settings/ModelsPage.tsx",
        '.filter((credential) => credential.capabilities.includes("chat"))',
        ".filter(() => true)",
        STUDIO_TESTS,
    ),
    (
        "the Studio sends the first model, not the chosen one",
        "frontend/apps/studio/src/settings/ModelsPage.tsx",
        "          { credential_id: credentialId, model },",
        '          { credential_id: credentialId, model: options[0]?.id ?? "" },',
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
clean = [run(GATEWAY_TESTS), run(DEFAULT_TESTS), run(STUDIO_TESTS)]
print(f"unmodified code: {'passes' if clean == [0, 0, 0] else f'FAILS {clean}'}")
sys.exit(0 if caught == len(MUTATIONS) and clean == [0, 0, 0] else 1)
