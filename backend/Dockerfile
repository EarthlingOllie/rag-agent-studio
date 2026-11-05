# Build stage: resolve the locked runtime dependencies into /opt/venv with uv.
FROM python:3.13-slim AS build

RUN pip install --no-cache-dir uv==0.11.32

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

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

RUN useradd --system --uid 10001 studio
USER studio

EXPOSE 8000
CMD ["python", "-m", "app.serve"]
