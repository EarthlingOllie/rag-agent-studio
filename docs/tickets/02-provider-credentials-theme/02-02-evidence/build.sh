#!/usr/bin/env bash
# Sandbox-only image build: the committed Dockerfiles, plus the egress proxy CA and proxy env in the first (download) stage.
# Usage: build.sh <checkout> [tag]. Uses the sandbox's $HTTPS_PROXY (host network).
set -euo pipefail
WT=$1; TAG=${2:-local}; OUT=$(mktemp -d)
inject() { awk -v extra="$2" 'NR==1,/^FROM/{ if (/^FROM/ && !done) { print; print extra; done=1; next } } { print }' "$1"; }
CA="COPY --from=sandboxca ca-bundle.crt /etc/ssl/certs/sandbox-ca.crt
ENV SSL_CERT_FILE=/etc/ssl/certs/sandbox-ca.crt PIP_CERT=/etc/ssl/certs/sandbox-ca.crt NODE_EXTRA_CA_CERTS=/etc/ssl/certs/sandbox-ca.crt HTTPS_PROXY=$HTTPS_PROXY https_proxy=$HTTPS_PROXY COREPACK_NPM_REGISTRY=https://registry.npmjs.org"
inject "$WT/backend/Dockerfile" "$CA" > "$OUT/Dockerfile.backend"
inject "$WT/frontend/Dockerfile" "$CA" > "$OUT/Dockerfile.frontend"
docker build --network host --build-context sandboxca=/root/.ccr -f "$OUT/Dockerfile.backend" -t rag-agent-studio/api:$TAG "$WT/backend"
docker build --network host --build-context sandboxca=/root/.ccr -f "$OUT/Dockerfile.frontend" -t rag-agent-studio/studio:$TAG "$WT/frontend"
