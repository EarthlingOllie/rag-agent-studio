#!/usr/bin/env bash
# Sandbox-only images: the committed Dockerfiles plus the proxy CA, minus the plain-HTTP apt upgrade.
set -euo pipefail
WT=$1; TAG=$2; OUT=$(dirname "$0")
CA='COPY --from=ca ca-bundle.crt /etc/ssl/ccr-ca.crt
ENV SSL_CERT_FILE=/etc/ssl/ccr-ca.crt REQUESTS_CA_BUNDLE=/etc/ssl/ccr-ca.crt PIP_CERT=/etc/ssl/ccr-ca.crt UV_NATIVE_TLS=1 NODE_EXTRA_CA_CERTS=/etc/ssl/ccr-ca.crt HF_HUB_DISABLE_XET=1'
fix() { awk -v extra="$CA" '/^FROM/{print; print extra; next} /^RUN apt-get update/{skip=1} skip{ if ($0 !~ /\\$/) skip=0; next } {print}' "$1"; }
fix "$WT/backend/Dockerfile" > "$OUT/backend.Dockerfile"
fix "$WT/frontend/Dockerfile" > "$OUT/frontend.Dockerfile"
PX="--build-arg HTTPS_PROXY=$HTTPS_PROXY --build-arg https_proxy=$HTTPS_PROXY"
docker build --progress plain --network host $PX --build-context ca=/root/.ccr -f "$OUT/frontend.Dockerfile" -t rag-agent-studio/studio:$TAG "$WT/frontend"
docker build --progress plain --network host $PX --build-context ca=/root/.ccr --build-context seed="$WT/seed" \
  --build-arg WITH_PDF=false --build-arg BUNDLE_MODELS=${BUNDLE_MODELS:-true} -f "$OUT/backend.Dockerfile" -t rag-agent-studio/api:$TAG "$WT/backend"
