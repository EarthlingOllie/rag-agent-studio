#!/usr/bin/env bash
# Every environment keeps its state in the bootstrap's S3 bucket with native locking (use_lockfile), not DynamoDB.
# terraform test cannot see backend blocks, so this reads each environment's backend.tf directly.
# Usage: infra/tests/backend.test.sh [infra-dir]
set -euo pipefail
infra=${1:-$(cd "$(dirname "$0")/.." && pwd)}
failures=0

fail() { echo "FAIL $1: $2"; failures=$((failures + 1)); }

envs=("$infra"/envs/*/)
[ -d "${envs[0]}" ] || { echo "FAIL no environments under $infra/envs"; exit 1; }

for env in "${envs[@]}"; do
  name=$(basename "$env")
  before=$failures
  file="$env/backend.tf"
  if [ ! -f "$file" ]; then fail "$name" "no backend.tf"; continue; fi
  # The backend "s3" block, without comments.
  block=$(sed -e 's/#.*//' "$file" | awk '/backend[[:space:]]+"s3"[[:space:]]*\{/ {inside=1} inside {print} inside && /^[[:space:]]*\}[[:space:]]*$/ {exit}')
  [ -n "$block" ] || { fail "$name" "no backend \"s3\" block"; continue; }
  grep -Eq '^[[:space:]]*use_lockfile[[:space:]]*=[[:space:]]*true[[:space:]]*$' <<<"$block" || fail "$name" "use_lockfile = true is missing"
  grep -Eq "^[[:space:]]*key[[:space:]]*=[[:space:]]*\"envs/$name/terraform.tfstate\"" <<<"$block" || fail "$name" "key must be envs/$name/terraform.tfstate"
  if grep -Eq '^[[:space:]]*(dynamodb_table|bucket|encrypt|kms_key_id)[[:space:]]*=' <<<"$block"; then
    fail "$name" "dynamodb_table, bucket, encrypt and kms_key_id must not be set (native locking; bucket from -backend-config; the bucket's KMS default encryption applies)"
  fi
  [ "$failures" -gt "$before" ] || echo "ok   $name: S3 backend with native locking"
done

exit $((failures > 0))
