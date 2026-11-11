"""RAG Agent Studio: the API, the worker and Beat."""

import os
import sys

# Docling's chunker uses Hugging Face transformers only for tokenizers, never PyTorch models.
# Without this, importing it prints an advisory about PyTorch to stderr, which isn't a JSON
# log line. Set before anything imports transformers.
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")


def _import_onnx_runtime_quietly() -> None:
    """Import ONNX Runtime (the local classifier, Embedding Model and OCR) with file descriptor
    2 closed off, then keep its own logging to errors.

    It logs from C++ straight to stderr, bypassing logging, and it already logs while it is
    imported, before its log level can be set: on some hosts it warns that it cannot read a
    device's PCI bus ID. Neither line would be JSON. Done here, before anything imports it."""
    sys.stderr.flush()
    saved = os.dup(2)
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull, 2)
        import onnxruntime
    finally:
        os.dup2(saved, 2)
        os.close(saved)
        os.close(devnull)
    onnxruntime.set_default_logger_severity(3)  # 3: errors and fatal only


_import_onnx_runtime_quietly()
