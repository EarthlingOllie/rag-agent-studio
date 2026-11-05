"""Mutation proof for ticket 03-09: each mutation breaks one behaviour, and the named tests
must then fail. Run from the repository root: ``python3 mutate.py`` (needs the test services;
set TEST_DATABASE_URL / TEST_REDIS_URL). The file is restored after each mutation."""

import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
TESTS = "tests/integration/test_embedding_models.py"

MUTATIONS = [
    (
        "the model can change while the Project has Documents",
        "backend/app/projects/embedding.py",
        "    if await session.scalar(select(exists().where(Document.project_id == project.id))):",
        "    if False and await session.scalar(select(exists().where(Document.project_id == project.id))):",
        "test_the_model_cannot_change_while_the_project_has_documents",
    ),
    (
        "a Project's credential isn't reported as a reference",
        "backend/app/projects/embedding.py",
        "            Project.embedding_credential_id == credential_id,\n        )",
        "            Project.embedding_credential_id == credential_id,\n            Project.id.is_(None),\n        )",
        "test_a_credential_a_project_embeds_with_cannot_be_deleted",
    ),
    (
        "the local model accepts a credential",
        "backend/app/projects/embedding.py",
        "        if credential_id is not None:\n            raise",
        "        if credential_id is not None and False:\n            raise",
        "test_an_impossible_choice_is_refused",
    ),
    (
        "a choice of the current model is audited again",
        "backend/app/projects/embedding.py",
        "    if (project.embedding_model_id, project.embedding_credential_id) == (model.id, credential_id):\n        return project",
        "    if False:\n        return project",
        "test_choosing_a_model_is_an_audit_event or test_choosing_the_current_model_again_is_allowed_with_documents",
    ),
    (
        "ingestion ignores the Project's provider model",
        "backend/app/documents/pipeline.py",
        "resolve_embedder(embedding_model(model_id), credential, ports.embedders, gateway)",
        "resolve_embedder(embedding_model('multilingual-e5-small'), credential, ports.embedders, gateway)",
        "test_an_editor_chooses_a_provider_model_and_documents_embed_with_it",
    ),
    (
        "provider vectors of the wrong size are accepted",
        "backend/app/embeddings/provider.py",
        "            if len(vector) != self._model.dimension:",
        "            if False:",
        "test_vectors_of_the_wrong_size_fail_the_document",
    ),
    (
        "the probe searches every Embedding Model's Chunks",
        "backend/app/retrieval/probe.py",
        "            Chunk.embedding_model_id == model.id,\n",
        "",
        "test_the_probe_skips_chunks_of_other_embedding_models",
    ),
    (
        "the probe searches every Project",
        "backend/app/retrieval/probe.py",
        "            Chunk.project_id == project.id,\n",
        "",
        "test_the_probe_only_searches_its_own_project",
    ),
    (
        "the probe returns the farthest Chunks first",
        "backend/app/retrieval/probe.py",
        ".order_by(distance, Chunk.id)",
        ".order_by(distance.desc(), Chunk.id)",
        "test_the_probe_returns_the_top_k_chunks_nearest_the_query",
    ),
    (
        "the probe ignores top_k",
        "backend/app/retrieval/probe.py",
        "        .limit(top_k)\n",
        "",
        "test_the_probe_returns_five_chunks_by_default",
    ),
]


def run(selection: str) -> int:
    command = ["uv", "run", "pytest", "-q", "--no-cov", "-p", "no:randomly", TESTS, "-k", selection]
    return subprocess.run(command, cwd=ROOT / "backend", capture_output=True, check=False).returncode


def main() -> int:
    caught = 0
    for name, path, old, new, tests in MUTATIONS:
        file = ROOT / path
        original = file.read_text()
        assert original.count(old) == 1, f"{name}: the code to mutate isn't there exactly once"
        file.write_text(original.replace(old, new))
        try:
            code = run(tests)
        finally:
            file.write_text(original)
        verdict = "CAUGHT" if code != 0 else "MISSED"
        caught += code != 0
        print(f"{verdict}: {name} ({path}) -> pytest -k '{tests}' exit {code}", flush=True)
    print(f"{caught}/{len(MUTATIONS)} mutations caught")
    clean = run("embedding or probe or model")
    print(f"unmodified code: {TESTS} exit {clean}")
    return 0 if caught == len(MUTATIONS) and clean == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
