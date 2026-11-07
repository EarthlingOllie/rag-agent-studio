#!/usr/bin/env bash
# Tears the demo environment down (spec 09 story 27), so it stops costing money. The destroy workflow runs it with
# the confirmation typed into its form; nothing happens unless that is exactly "destroy demo". The state bucket and
# the OIDC deploy role (infra/bootstrap) are not touched.
# Usage: TF_STATE_BUCKET=... AWS_REGION=... scripts/deploy/destroy.sh "<typed confirmation>"
# Optional: DEPLOY_ROOT (default infra/envs/demo).
set -euo pipefail

expected="destroy demo"
[ $# -eq 1 ] || { echo "usage: $0 \"$expected\"" >&2; exit 2; }
if [ "$1" != "$expected" ]; then
  echo "::error title=Not destroyed::Type exactly '$expected' to destroy the demo environment. Nothing was changed." >&2
  exit 1
fi
[ -n "${TF_STATE_BUCKET:-}" ] || { echo "TF_STATE_BUCKET must name the bootstrap's state bucket (its state_bucket_name output)." >&2; exit 2; }
[ -n "${AWS_REGION:-}" ] || { echo "AWS_REGION must be set." >&2; exit 2; }
root=${DEPLOY_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)/infra/envs/demo}

terraform -chdir="$root" init -input=false -backend-config="bucket=$TF_STATE_BUCKET" -backend-config="region=$AWS_REGION"
terraform -chdir="$root" destroy -input=false -auto-approve
echo "The demo environment is destroyed."
