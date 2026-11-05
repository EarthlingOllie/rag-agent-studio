# Build stage: resolve the locked runtime dependencies into /opt/venv with uv.
FROM python:3.13-slim AS build

RUN pip install --no-cache-dir uv==0.11.32

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

# PDF conversion needs Docling's PDF backend and layout models (PyTorch, CPU build).
ARG WITH_PDF=true

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project $([ "$WITH_PDF" = "true" ] && echo --group pdf)

# Runtime stage: the virtualenv and the app only. uv, pip and pip's vendored libraries are
# not needed at runtime, and the Trivy gate (security.yml) rejects their known CVEs.
FROM python:3.13-slim

# Debian security fixes released after the base image was built (the Trivy gate fails on fixable HIGH ones).
RUN apt-get update \
    && apt-get upgrade --yes --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip uninstall --yes --no-cache-dir pip \
    && rm -rf /usr/local/lib/python3.13/ensurepip

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

COPY --from=build /opt/venv /opt/venv

WORKDIR /app

COPY alembic.ini ./
COPY app ./app
COPY migrations ./migrations

# The local Embedding Model, its tokenizer and (with PDF) Docling's layout models are downloaded
# at build time, so the worker doesn't fetch them at startup.
ARG WITH_PDF=true
ARG BUNDLE_MODELS=true
ENV HF_HOME=/opt/models/huggingface \
    FASTEMBED_CACHE_PATH=/opt/models/fastembed \
    DOCLING_ARTIFACTS_PATH=/opt/models/docling
# The Docling folder always exists: Docling refuses an artifacts path that isn't a directory, even for
# formats that need no models, so an image built without the models still converts Markdown, DOCX and PPTX.
RUN mkdir -p /opt/models/docling \
    && if [ "$BUNDLE_MODELS" = "true" ]; then \
        python -c "from app.embeddings.local import LocalEmbedder as E; e = E(); e.embed_passages(['warm up']); e.tokenizer(512)" \
        && if [ "$WITH_PDF" = "true" ]; then \
            python -c "from docling.utils.model_downloader import download_models; from pathlib import Path; download_models(output_dir=Path('/opt/models/docling'))"; \
        fi; \
    fi

RUN useradd --system --uid 10001 studio
USER studio

EXPOSE 8000
CMD ["python", "-m", "app.serve"]
