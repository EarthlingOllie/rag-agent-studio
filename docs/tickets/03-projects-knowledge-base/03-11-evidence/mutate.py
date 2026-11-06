"""Mutation proof for ticket 03-11: each mutant must make the deletion tests fail.
Run from backend/ with the test services' env (see checks.sh)."""

import pathlib
import subprocess
import sys

TESTS = [
    "tests/integration/test_project_deletion.py",
    "tests/integration/test_object_store.py",
    "-k",
    "deletion or prefix or permanently or owner or archived or name or unknown or cascade",
]
MUTANTS = [
    ("app/projects/service.py", "    if project.archived_at is None:\n        raise ProjectNotArchivedError\n    if confirm_name", "    if confirm_name", "an active Project may be deleted"),
    ("app/projects/service.py", "if confirm_name != project.name:", "if confirm_name.strip().lower() != project.name.lower():", "the name is matched loosely"),
    ("app/projects/service.py", "if project is None or project.archived_at is None:", "if project is None:", "the cascade ignores a restore"),
    ("app/projects/service.py", 'action="project.deleted"', 'action="project.archived"', "the deletion is audited as something else"),
    ("app/projects/service.py", "occurred_at=requested_at,", "occurred_at=None,", "the Audit Event takes the database's time"),
    ("app/projects/tasks.py", "    if prefix is not None:\n        await current_ports().object_store.delete_prefix(prefix)", "    pass", "stored files are kept"),
    ("app/projects/api.py", "scope: OwnerScope, db: Db, clock: ClockDep\n) -> Response:", "scope: Scope, db: Db, clock: ClockDep\n) -> Response:", "Editors may delete"),
    ("app/storage/s3.py", "            if keys:\n                self._client.delete_objects(\n                    Bucket=self.bucket, Delete={\"Objects\": keys, \"Quiet\": True}\n                )", "            if keys:\n                self._client.delete_objects(\n                    Bucket=self.bucket, Delete={\"Objects\": keys, \"Quiet\": True}\n                )\n                break", "S3 deletes only the first page"),
    ("app/storage/memory.py", "if key.startswith(prefix)]", "if key.startswith(prefix.rstrip('/'))]", "the fake deletes sibling prefixes"),
]
failures = 0
for path, old, new, what in MUTANTS:
    file = pathlib.Path(path)
    original = file.read_text()
    assert original.count(old) == 1, (path, old)
    file.write_text(original.replace(old, new))
    try:
        result = subprocess.run(["uv", "run", "pytest", "--no-cov", "-q", "-p", "no:logging", "-x", *TESTS], capture_output=True, text=True)
    finally:
        file.write_text(original)
    caught = result.returncode != 0
    failures += not caught
    print(f"{'CAUGHT ' if caught else 'SURVIVED'} {what}: {result.stdout.strip().splitlines()[-1]}", flush=True)
clean = subprocess.run(["uv", "run", "pytest", "--no-cov", "-q", "-p", "no:logging", *TESTS], capture_output=True, text=True)
print(f"unmodified: {clean.stdout.strip().splitlines()[-1]}")
sys.exit(1 if failures or clean.returncode else 0)
