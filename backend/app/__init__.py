"""RAG Agent Studio: the API, the worker and Beat."""

import os

# Docling's chunker uses Hugging Face transformers only for tokenizers, never PyTorch models.
# Without this, importing it prints an advisory about PyTorch to stderr, which isn't a JSON
# log line. Set before anything imports transformers.
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
