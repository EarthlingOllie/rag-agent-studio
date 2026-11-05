#!/usr/bin/env bash
# Each case copies the branch's infra/ and scripts/ to a temporary directory, makes one bad change, and runs the gate
# that should catch it. Every case must exit non-zero. Usage: gate-demo.sh <repo root>
set -uo pipefail
root=$1
strip() { sed 's/\x1b\[[0-9;]*m//g'; }
case_() { # name, file, sed expression, command (run from the copy's root)
  local work; work=$(mktemp -d)
  cp -r "$root/infra" "$root/scripts" "$work/"
  find "$work/infra" -name .terraform -prune -exec rm -rf {} + 2>/dev/null
  sed -i "$3" "$work/$2"
  echo "== $1"
  echo "   change: $2: sed '$3'"
  echo "   \$ $4"
  (cd "$work" && eval "$4") 2>&1 | strip | grep -E '^(FAIL|  run ".*"\.\.\. fail|Error: Test assertion failed|Check: |Failure!|Passed checks)' | sed 's/^/   /' | head -12
  echo "   exit=${PIPESTATUS[0]}"
  rm -rf "$work"; echo
}
tftest='terraform -chdir=$D init -backend=false -input=false >/dev/null && terraform -chdir=$D test -no-color'
case_ "Trust any repository" infra/modules/ci-oidc/main.tf 's/"repo:${var.github_repository}:${claim}"/"repo:*:${claim}"/' "D=infra/modules/ci-oidc; $tftest"
case_ "Drop the audience condition" infra/modules/ci-oidc/main.tf '/StringEquals = /d' "D=infra/modules/ci-oidc; $tftest"
case_ "Suspend state versioning" infra/bootstrap/main.tf '/versioning_configuration {/,/}/ s/status = "Enabled"/status = "Suspended"/' "D=infra/bootstrap; $tftest"
case_ "Encrypt state with SSE-S3 instead of KMS" infra/bootstrap/main.tf 's/sse_algorithm     = "aws:kms"/sse_algorithm     = "AES256"/' "D=infra/bootstrap; $tftest"
case_ "Allow a public bucket policy" infra/bootstrap/main.tf 's/block_public_policy     = true/block_public_policy     = false/' "D=infra/bootstrap; $tftest"
case_ "Turn off key rotation (terraform test)" infra/bootstrap/main.tf 's/enable_key_rotation     = true/enable_key_rotation     = false/' "D=infra/bootstrap; $tftest"
case_ "Turn off key rotation (checkov)" infra/bootstrap/main.tf 's/enable_key_rotation     = true/enable_key_rotation     = false/' "cd infra && checkov --config-file .checkov.yaml"
case_ "Turn off native locking" infra/envs/demo/backend.tf 's/use_lockfile = true/use_lockfile = false/' "infra/tests/backend.test.sh infra"
case_ "Lock with DynamoDB instead" infra/envs/demo/backend.tf 's/use_lockfile = true/dynamodb_table = "locks"/' "infra/tests/backend.test.sh infra"
case_ "Plan even without the secret" scripts/ci/plan-gate.sh 's/if \[ -z "${AWS_ROLE_ARN:-}" \]; then/if false; then/' "scripts/ci/tests/plan-gate.test.sh"
case_ "Plan on every pull request" scripts/ci/plan-gate.sh 's/if ! grep -Eq/if false \&\& grep -Eq/' "scripts/ci/tests/plan-gate.test.sh"
