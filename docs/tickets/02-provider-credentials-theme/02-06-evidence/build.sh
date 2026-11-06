#!/usr/bin/env bash
# Sandbox-only `make images`: the same two `docker build`s as the Makefile's `images` target, on the
# committed Dockerfiles with only the egress proxy's CA and proxy env added to the first stage.
# WITH_PDF=false and BUNDLE_MODELS=false: Hugging Face (models) is blocked by this sandbox's
# egress policy and the shared disk is short, so PyTorch and the models can't be installed here.
set -euo pipefail
WT=$1; TAG=${2:-local}; OUT=$(dirname "$(readlink -f "$0")")
inject() { awk -v extra="$2" 'NR==1,/^FROM/{ if (/^FROM/ && !done) { print; print extra; done=1; next } } { print }' "$1"; }
CA="COPY --from=sandboxca ca-bundle.crt /etc/ssl/certs/sandbox-ca.crt
ENV SSL_CERT_FILE=/etc/ssl/certs/sandbox-ca.crt PIP_CERT=/etc/ssl/certs/sandbox-ca.crt NODE_EXTRA_CA_CERTS=/etc/ssl/certs/sandbox-ca.crt HTTPS_PROXY=$HTTPS_PROXY https_proxy=$HTTPS_PROXY COREPACK_NPM_REGISTRY=https://registry.npmjs.org"
inject "$WT/backend/Dockerfile" "$CA" > "$OUT/Dockerfile.backend"
inject "$WT/frontend/Dockerfile" "$CA" > "$OUT/Dockerfile.frontend"
echo "+ docker build -t rag-agent-studio/api:$TAG backend (WITH_PDF=false BUNDLE_MODELS=false, sandbox CA)"
docker build --progress plain --network host --build-context sandboxca=/root/.ccr --build-arg WITH_PDF=false --build-arg BUNDLE_MODELS=false \
  -f "$OUT/Dockerfile.backend" -t rag-agent-studio/api:$TAG "$WT/backend"
echo "+ docker build -t rag-agent-studio/studio:$TAG frontend (sandbox CA)"
docker build --progress plain --network host --build-context sandboxca=/root/.ccr -f "$OUT/Dockerfile.frontend" -t rag-agent-studio/studio:$TAG "$WT/frontend"
