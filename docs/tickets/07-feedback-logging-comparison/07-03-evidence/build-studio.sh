#!/usr/bin/env bash
# The Studio half of build.sh only (same sandbox CA injection), for a rerun where the API
# image's inputs (backend/app, migrations, lockfile, Dockerfile) have not changed.
set -euo pipefail
WT=$1; TAG=${2:-local}
inject() { awk -v extra="$2" '/^FROM/{ print; print extra; next } { print }' "$1"; }
CA="COPY --from=sandboxca ca-bundle.crt /etc/ssl/certs/sandbox-ca.crt
ENV SSL_CERT_FILE=/etc/ssl/certs/sandbox-ca.crt REQUESTS_CA_BUNDLE=/etc/ssl/certs/sandbox-ca.crt PIP_CERT=/etc/ssl/certs/sandbox-ca.crt NODE_EXTRA_CA_CERTS=/etc/ssl/certs/sandbox-ca.crt HTTPS_PROXY=$HTTPS_PROXY https_proxy=$HTTPS_PROXY HF_HUB_DISABLE_XET=1 COREPACK_NPM_REGISTRY=https://registry.npmjs.org"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
inject "$WT/frontend/Dockerfile" "$CA" > "$TMP/Dockerfile.frontend"
echo "+ docker build -t rag-agent-studio/studio:$TAG frontend (sandbox CA)"
docker build --progress plain --network host --build-context sandboxca=/root/.ccr -f "$TMP/Dockerfile.frontend" -t rag-agent-studio/studio:$TAG "$WT/frontend"
docker image inspect rag-agent-studio/api:$TAG --format 'api image reused: {{.Id}} created {{.Created}}'
