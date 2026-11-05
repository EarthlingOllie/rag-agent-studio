"""Mutation proof: each mutation breaks one behaviour; the named tests must fail. Then the
unmodified code must pass. Run from backend/ of the worktree: python mutate.py"""

import subprocess
import sys
from pathlib import Path

MUTATIONS = [
    ("app/documents/pipeline.py", "await _set_status(session, document, DocumentStatus.READY, markdown=markdown_key(document))",
     "await _set_status(session, document, DocumentStatus.PROCESSING, markdown=markdown_key(document))",
     "tests/integration/test_documents.py"),
    ("app/documents/service.py", "    digest = hashlib.sha256(data).hexdigest()", "    digest = hashlib.md5(data).hexdigest()  # noqa: S324",
     "tests/integration/test_documents.py"),
    ("app/documents/service.py", "    if content_hash is not None and content_hash.lower() != digest:",
     "    if False:", "tests/integration/test_documents.py"),
    ("app/documents/service.py", "    project = await projects.active_project(session, scope, project_id)\n    content_type",
     "    project = await projects.get_project(session, scope, project_id)\n    content_type", "tests/integration/test_documents.py"),
    ("app/documents/service.py", "    if size_bytes > max_bytes:", "    if size_bytes > max_bytes + 1:", "tests/integration/test_documents.py"),
    ("app/documents/service.py", "    await redis.delete(key)\n", "", "tests/integration/test_documents.py"),
    ("app/documents/chunking.py", "    chunker = HybridChunker(tokenizer=tokenizer)",
     "    chunker = HybridChunker(tokenizer=type(tokenizer)(max_tokens=10_000))", "tests/unit/test_chunking.py"),
    ("app/documents/chunking.py", "                heading_path=list(meta.headings or []),", "                heading_path=[],",
     "tests/unit/test_chunking.py tests/integration/test_documents.py"),
    ("app/documents/pipeline.py", "        tokenizer = embedder.tokenizer(min(chunk_max_tokens, embedder.model.max_tokens))",
     "        tokenizer = embedder.tokenizer(embedder.model.max_tokens)", "tests/integration/test_documents.py"),
    # The database is built by the migration, so the full-text column is mutated there; the
    # migration round trip runs first so the mutated schema is the one under test.
    ("migrations/versions/20261105_0008_documents.py", "sa.Computed(\"to_tsvector('simple'::regconfig, text)\", persisted=True)",
     "sa.Computed(\"to_tsvector('simple'::regconfig, '')\", persisted=True)",
     "tests/integration/test_migrations.py tests/integration/test_chunk_storage.py"),
    ("migrations/versions/20261105_0008_documents.py", "USING hnsw ((embedding::vector(384)) vector_cosine_ops)",
     "USING hnsw ((embedding::vector(384)) vector_l2_ops)",
     "tests/integration/test_migrations.py tests/integration/test_chunk_storage.py"),
    ("app/projects/service.py", "ProjectSummary(project, document_count=counts.get(project.id, 0), agent_count=0)",
     "ProjectSummary(project, document_count=0, agent_count=0)", "tests/integration/test_documents.py"),
    ("app/documents/converter.py", "            if paragraph and (heading or not line.strip()):", "            if paragraph and heading:",
     "tests/integration/test_documents.py"),
    ("app/storage/s3.py", "            if error.response.get(\"Error\", {}).get(\"Code\") in _MISSING:\n                raise ObjectNotFoundError(key) from None",
     "            if False:\n                raise ObjectNotFoundError(key) from None", "tests/integration/test_object_store.py"),
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
    print(f"{number:2}. {verdict}  {path}: {old.strip().splitlines()[0][:70]!r} -> {new.strip().splitlines()[0][:50] if new.strip() else '(removed)'!r}  [{tests}]", flush=True)

print(f"\n{caught}/{len(MUTATIONS)} mutations caught")
clean = run("tests/integration/test_migrations.py tests/integration/test_chunk_storage.py tests/integration/test_documents.py tests/unit/test_chunking.py tests/integration/test_object_store.py tests/integration/test_migrations.py")
print(f"unmodified code: {'passes' if clean == 0 else 'FAILS'}")
