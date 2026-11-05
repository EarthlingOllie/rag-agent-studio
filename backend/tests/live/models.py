"""Whether the live suite can get the Hugging Face models a test needs.

A test that needs a model calls ``require_models``. It runs when the model is already on disk
(the worker image bundles them; see the Dockerfile) or Hugging Face answers. Otherwise it is
skipped with the reason, so a run without network access says what it didn't cover instead of
failing on the download. ``LIVE_REQUIRE_MODELS=1`` turns that skip into a failure, for runs
that must cover everything (a release check, or a machine that should have the models).
"""

import os
from pathlib import Path

import httpx
import pytest
from huggingface_hub import snapshot_download

# Docling's default PDF layout model, and the local Embedding Model with its tokenizer.
DOCLING_LAYOUT = "docling-project/docling-layout-heron"
LOCAL_EMBEDDING_MODEL = "intfloat/multilingual-e5-small"


def _on_disk(repo_id: str) -> bool:
    if repo_id.startswith("docling-project/"):
        artifacts = os.environ.get("DOCLING_ARTIFACTS_PATH")
        if artifacts and (Path(artifacts) / repo_id.replace("/", "--")).is_dir():
            return True
    try:
        snapshot_download(repo_id, local_files_only=True)
    except Exception:  # any miss means "not cached"
        return False
    return True


def _unreachable(repo_id: str) -> str | None:
    """Why Hugging Face can't serve the model, or None when it can."""
    url = f"https://huggingface.co/api/models/{repo_id}"
    try:
        response = httpx.head(url, timeout=10, follow_redirects=True)
    except httpx.HTTPError as error:
        return f"{url}: {type(error).__name__}: {error}"
    if response.status_code >= 400:
        return f"{url}: HTTP {response.status_code}"
    return None


def require_models(*repo_ids: str) -> None:
    for repo_id in repo_ids:
        if _on_disk(repo_id):
            continue
        reason = _unreachable(repo_id)
        if reason is None:
            continue
        message = (
            f"Hugging Face model {repo_id} is not on disk and can't be downloaded ({reason}). "
            "Run the live suite where huggingface.co is reachable, or in the worker image."
        )
        if os.environ.get("LIVE_REQUIRE_MODELS") == "1":
            pytest.fail(message)
        pytest.skip(message)
