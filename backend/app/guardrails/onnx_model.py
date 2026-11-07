"""The local injection classifier's model: Protect AI's ``deberta-v3-base-prompt-injection-v2``
(Apache-2.0), a DeBERTa-v3 classifier with two classes, ``SAFE`` and ``INJECTION``, in its
ONNX export, run with ONNX Runtime on the CPU.

The model, its tokenizer and its config come from Hugging Face at a pinned revision. The API
image downloads them at build time (``BUNDLE_MODELS``, see the Dockerfile), so the API reads
them from its Hugging Face cache and never fetches them at runtime; elsewhere they are fetched on
first use. This adapter needs those files, so it is exercised by the live suite
(``tests/live``), outside the coverage gate (ADR-0008), like the local Embedding Model.
"""

import json
from pathlib import Path

import onnxruntime
from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer

from app.guardrails.local import LoadedModel

REPO = "protectai/deberta-v3-base-prompt-injection-v2"
REVISION = "90c9989b1a342275dd0d1a95aad283c04e075671"
FILES = ("onnx/model.onnx", "onnx/tokenizer.json", "onnx/config.json")


def download() -> Path:
    """The folder holding the model's files, downloading any not yet in the cache."""
    paths = [Path(hf_hub_download(REPO, name, revision=REVISION)) for name in FILES]
    return paths[0].parent


def load() -> LoadedModel:
    folder = download()
    config = json.loads((folder / "config.json").read_text())
    tokenizer = Tokenizer.from_file(str(folder / "tokenizer.json"))
    tokenizer.no_truncation()
    tokenizer.no_padding()
    options = onnxruntime.SessionOptions()
    # One request's windows are scored one after another; keep each to a couple of threads so
    # concurrent requests share the CPU.
    options.intra_op_num_threads = 2
    session = onnxruntime.InferenceSession(
        str(folder / "model.onnx"), options, providers=["CPUExecutionProvider"]
    )

    def tokenize(text: str) -> list[int]:
        ids: list[int] = tokenizer.encode(text, add_special_tokens=False).ids
        return ids

    cls_id = tokenizer.token_to_id("[CLS]")
    sep_id = tokenizer.token_to_id("[SEP]")
    if cls_id is None or sep_id is None:
        raise ValueError("The classifier's tokenizer has no [CLS] or [SEP] token")
    return LoadedModel(
        session=session,
        tokenize=tokenize,
        cls_id=cls_id,
        sep_id=sep_id,
        injection_index=int(config["label2id"]["INJECTION"]),
        max_tokens=int(config["max_position_embeddings"]),
    )
