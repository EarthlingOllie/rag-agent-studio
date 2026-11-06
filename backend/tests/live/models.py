"""Whether the live suite can get the Hugging Face models a test needs.

A test that needs a model calls ``require_models``. It runs when the model is already on disk
(the worker image bundles them; see the Dockerfile) or can be downloaded from Hugging Face.
Otherwise it is skipped with the reason, so a run without network access says what it didn't
cover instead of failing on the download. ``LIVE_REQUIRE_MODELS=1`` turns that skip into a
failure, for runs that must cover everything (a release check, or a machine that should have
the models).
"""

import os
from pathlib import Path

import httpx
import pytest
from huggingface_hub import hf_hub_url, snapshot_download

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


# The weight files each model's code loads. A repo can hold several exports of the same
# weights (multilingual-e5-small has PyTorch, safetensors, OpenVINO and four ONNX files, about
# 2.3 GB); only the one the code reads is checked, and the code downloads it on first use.
WEIGHT_FILES = {
    DOCLING_LAYOUT: ("model.safetensors",),
    LOCAL_EMBEDDING_MODEL: ("onnx/model.onnx",),
}


def _unreachable(repo_id: str) -> str | None:
    """Why the model can't be downloaded, or None when it can.

    Hugging Face serves weight files from a CDN, not huggingface.co, so a network can reach
    the one but not the other. The first byte of each weight file the code loads is fetched
    with a short timeout: a blocked CDN then skips in seconds, where a download would retry
    for a long time. The code under test then downloads what it needs.
    """
    try:
        for name in WEIGHT_FILES[repo_id]:
            httpx.get(
                hf_hub_url(repo_id, name),
                headers={"Range": "bytes=0-0"},
                timeout=10,
                follow_redirects=True,
            ).raise_for_status()
    except httpx.HTTPError as error:
        return f"{error.request.url.host}: {type(error).__name__}: {str(error)[:300]}"
    return None


# RapidOCR's models (for OCR) come from ModelScope, not Hugging Face. Docling's
# ``download_models`` puts them under the artifacts path's ``RapidOcr`` folder.
RAPIDOCR_MODELS_URL = "https://www.modelscope.cn/models/RapidAI/RapidOCR"


def _skip_or_fail(message: str) -> None:
    if os.environ.get("LIVE_REQUIRE_MODELS") == "1":
        pytest.fail(message)
    pytest.skip(message)


def require_ocr_models() -> None:
    """RapidOCR's models: on disk with Docling's (the worker image), or downloadable."""
    artifacts = os.environ.get("DOCLING_ARTIFACTS_PATH")
    if artifacts and (Path(artifacts) / "RapidOcr").is_dir():
        return
    try:
        httpx.head(RAPIDOCR_MODELS_URL, timeout=10, follow_redirects=True).raise_for_status()
    except httpx.HTTPError as error:
        _skip_or_fail(
            f"RapidOCR's models are not on disk and can't be downloaded ({RAPIDOCR_MODELS_URL}: "
            f"{type(error).__name__}: {error}). Run the live suite where www.modelscope.cn is "
            "reachable, or in the worker image."
        )


def require_models(*repo_ids: str) -> None:
    for repo_id in repo_ids:
        if _on_disk(repo_id):
            continue
        reason = _unreachable(repo_id)
        if reason is None:
            continue
        message = (
            f"Hugging Face model {repo_id} is not on disk and can't be downloaded ({reason}). "
            "Run the live suite where huggingface.co and its CDN are reachable, or in the worker "
            "image."
        )
        _skip_or_fail(message)
