"""Mutation proof for ticket 03-05: each mutation breaks one behaviour; the named tests must
fail. Then the unmodified code must pass. Run from backend/ of the worktree with
TEST_DATABASE_URL and TEST_REDIS_URL set: python mutate.py"""

import subprocess
import sys
from pathlib import Path

T = "tests/integration/test_document_editions.py"
MUTATIONS = [
    # Dedupe
    ("app/documents/service.py", "    if duplicate is not None:", "    if False:", T),
    ("app/documents/service.py", "        StagedEdition.status != DocumentStatus.FAILED,",
     "        StagedEdition.status == DocumentStatus.FAILED,", T),
    ("app/documents/service.py", "        await store.delete(pending[\"object_key\"])\n", "", T),
    # Delete
    ("app/documents/service.py", "    await session.execute(delete(Chunk).where(Chunk.document_id == document.id))\n", "", T),
    ("app/documents/service.py", "        action=\"document.deleted\",", "        action=\"document.removed\",", T),
    ("app/documents/api.py", "    await enqueue_object_deletion(keys)\n", "", T),
    ("app/documents/service.py", "        keys += stored_keys(staged.object_key)\n", "", T),
    ("app/documents/service.py", "    project = await projects.active_project(session, scope, project_id)\n    document = await session.scalar(",
     "    project = await projects.get_project(session, scope, project_id)\n    document = await session.scalar(", T),
    # Replace
    ("app/documents/pipeline.py", "            replaced = await _swap(session, document) if job.staged else []",
     "            replaced = []", T),
    ("app/documents/pipeline.py", "        delete(Chunk).where(Chunk.document_id == document.id, Chunk.edition != staged.edition)",
     "        delete(Chunk).where(Chunk.document_id == document.id, Chunk.edition == -1)", T),
    ("app/documents/pipeline.py", "    elif replaced:\n        await delete_objects(replaced)\n", "", T),
    ("app/documents/pipeline.py", "            if job.staged:\n                failed = await session.get_one(StagedEdition, document.id, with_for_update=True)\n", "", T),
    ("app/documents/service.py", "    if document.status not in FINAL_STATUSES or (", "    if False and (", T),
    ("app/documents/service.py", "    staged.edition = document.edition + 1", "    staged.edition = document.edition", T),
    ("app/documents/pipeline.py", "    if document is None:\n        # Deleted while", "    if False:\n        # Deleted while", T),
]


def run(tests: str) -> int:
    command = ["uv", "run", "pytest", "-q", "-x", "--no-cov", "-p", "no:cacheprovider", *tests.split()]
    return subprocess.run(command, capture_output=True, text=True, check=False).returncode


caught = 0
for number, (path, old, new, tests) in enumerate(MUTATIONS, start=1):
    file = Path(path)
    original = file.read_text()
    if original.count(old) != 1:
        sys.exit(f"mutation {number}: pattern not found once in {path}")
    file.write_text(original.replace(old, new))
    try:
        code = run(tests)
    finally:
        file.write_text(original)
    verdict = "CAUGHT" if code != 0 else "SURVIVED"
    caught += code != 0
    print(f"{number:2}. {verdict}  {path}: {old.strip().splitlines()[0][:70]!r} -> {new.strip().splitlines()[0][:50] if new.strip() else '(removed)'!r}", flush=True)

print(f"\n{caught}/{len(MUTATIONS)} mutations caught")
print(f"unmodified code: {'passes' if run(T) == 0 else 'FAILS'}")
