#!/usr/bin/env bash
# Sandbox `make images` with the Dockerfile defaults (WITH_PDF=true BUNDLE_MODELS=true): the same
# two `docker build`s as the Makefile's `images` target, with only these sandbox additions, after
# every FROM: the egress proxy's CA and proxy env (PyPI, npm and Hugging Face are reached through
# it), and HF_HUB_DISABLE_XET=1 (Hugging Face's Xet transfer hosts aren't on this sandbox's
# allowlist; huggingface.co and its CDN are). BUNDLE_OCR_MODELS=false: RapidOCR's models come
# from www.modelscope.cn, which this sandbox's proxy refuses.
set -euo pipefail
WT=$1; TAG=${2:-pdf}; OUT=$(dirname "$(readlink -f "$0")")
inject() { awk -v extra="$2" '{ print } /^FROM/ { print extra }' "$1"; }
CA="COPY --from=sandboxca ca-bundle.crt /etc/ssl/certs/sandbox-ca.crt
ENV SSL_CERT_FILE=/etc/ssl/certs/sandbox-ca.crt REQUESTS_CA_BUNDLE=/etc/ssl/certs/sandbox-ca.crt PIP_CERT=/etc/ssl/certs/sandbox-ca.crt NODE_EXTRA_CA_CERTS=/etc/ssl/certs/sandbox-ca.crt HTTPS_PROXY=$HTTPS_PROXY https_proxy=$HTTPS_PROXY COREPACK_NPM_REGISTRY=https://registry.npmjs.org HF_HUB_DISABLE_XET=1"
TMP=$(mktemp -d)
inject "$WT/backend/Dockerfile" "$CA" > "$TMP/Dockerfile.backend"
inject "$WT/frontend/Dockerfile" "$CA" > "$TMP/Dockerfile.frontend"
echo "+ docker build -t rag-agent-studio/api:$TAG backend (Dockerfile defaults: WITH_PDF=true BUNDLE_MODELS=true; BUNDLE_OCR_MODELS=false; sandbox CA)"
docker build --progress plain --network host --build-context sandboxca=/root/.ccr --build-arg BUNDLE_OCR_MODELS=false \
  -f "$TMP/Dockerfile.backend" -t rag-agent-studio/api:$TAG "$WT/backend"
echo "+ docker build -t rag-agent-studio/studio:$TAG frontend (sandbox CA)"
docker build --progress plain --network host --build-context sandboxca=/root/.ccr -f "$TMP/Dockerfile.frontend" -t rag-agent-studio/studio:$TAG "$WT/frontend"
rm -rf "$TMP"
