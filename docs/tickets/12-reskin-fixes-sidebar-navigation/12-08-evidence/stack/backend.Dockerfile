# Build stage: resolve the locked runtime dependencies into /opt/venv with uv.
FROM python:3.13-slim AS build
COPY --from=ca ca-bundle.crt /etc/ssl/ccr-ca.crt
ENV SSL_CERT_FILE=/etc/ssl/ccr-ca.crt REQUESTS_CA_BUNDLE=/etc/ssl/ccr-ca.crt PIP_CERT=/etc/ssl/ccr-ca.crt UV_NATIVE_TLS=1

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
# (sandbox: apt upgrade skipped, plain-HTTP apt is blocked by the agent proxy)

RUN python -m pip uninstall --yes --no-cache-dir pip \
    && rm -rf /usr/local/lib/python3.13/ensurepip

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

COPY --from=build /opt/venv /opt/venv

WORKDIR /app

COPY alembic.ini ./
COPY app ./app
COPY migrations ./migrations

# The demo Documents, so the seed (`python -m app.seed`, whose default assets folder is /seed) also
# runs as a one-off ECS task in AWS (ticket 10-05). They live in the repository's seed folder, which
# every build passes as the `seed` build context (Makefile `images`, docker-compose.yml). `make seed`
# mounts the same folder over this one.
COPY --from=seed documents /seed/documents

# The local Embedding Model, its tokenizer, the input Guardrail's prompt-injection classifier
# (ONNX, loaded once here to check it works) and (with PDF) the Docling models the PDF pipeline
# uses (layout, table structure and RapidOCR's) are downloaded at build time, so the worker
# doesn't fetch them at startup. ``embed_passages`` is a coroutine, so it is run to load the model.
# RapidOCR's models come from ModelScope, not Hugging Face; BUNDLE_OCR_MODELS=false leaves them
# out for a network that can't reach it (OCR then fails until they can be fetched).
ARG WITH_PDF=true
ARG BUNDLE_MODELS=true
ARG BUNDLE_OCR_MODELS=true
ENV HF_HOME=/opt/models/huggingface \
    FASTEMBED_CACHE_PATH=/opt/models/fastembed \
    DOCLING_ARTIFACTS_PATH=/opt/models/docling
# The Docling folder always exists: Docling refuses an artifacts path that isn't a directory, even for
# formats that need no models, so an image built without the models still converts Markdown, DOCX and PPTX.
RUN mkdir -p /opt/models/docling \
    && if [ "$BUNDLE_MODELS" = "true" ]; then \
        python -c "import asyncio; from app.embeddings.local import LocalEmbedder as E; e = E(); asyncio.run(e.embed_passages(['warm up'])); e.tokenizer(512)" \
        && python -c "from app.guardrails import onnx_model; onnx_model.load()" \
        && if [ "$WITH_PDF" = "true" ]; then \
            python -c "from docling.utils.model_downloader import download_models; from pathlib import Path; download_models(output_dir=Path('/opt/models/docling'), with_code_formula=False, with_picture_classifier=False, with_rapidocr='$BUNDLE_OCR_MODELS' == 'true')"; \
        fi; \
    fi

RUN useradd --system --uid 10001 studio
USER studio

EXPOSE 8000
CMD ["python", "-m", "app.serve"]
