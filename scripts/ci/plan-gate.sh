#!/usr/bin/env bash
# Decides whether infra.yml's `terraform plan` job runs for a pull request (spec 09, user story 28).
# Writes run=true or run=false to $GITHUB_OUTPUT. The plan job is skipped, not failed, when the AWS_DEPLOY_ROLE_ARN
# secret is absent or the pull request touches no infrastructure. A role without the state bucket variable is a
# misconfiguration and fails.
# Usage: AWS_ROLE_ARN=... TF_STATE_BUCKET=... scripts/ci/plan-gate.sh <base sha> <head sha>
set -euo pipefail
[ $# -eq 2 ] || { echo "usage: $0 <base sha> <head sha>" >&2; exit 2; }
base=$1 head=$2
: "${GITHUB_OUTPUT:?GITHUB_OUTPUT must be set}"

if [ -z "${AWS_ROLE_ARN:-}" ]; then
  echo "run=false" >>"$GITHUB_OUTPUT"
  echo "::notice title=terraform plan skipped::The AWS_DEPLOY_ROLE_ARN secret is not configured, so there is nothing to plan against."
  exit 0
fi

changed=$(git diff --name-only "$base...$head")
if ! grep -Eq '^(infra/|\.github/workflows/infra\.yml$)' <<<"$changed"; then
  echo "run=false" >>"$GITHUB_OUTPUT"
  echo "::notice title=terraform plan skipped::This pull request changes nothing under infra/ or in the infra workflow."
  exit 0
fi

if [ -z "${TF_STATE_BUCKET:-}" ]; then
  echo "::error title=terraform plan misconfigured::AWS_DEPLOY_ROLE_ARN is set but the TF_STATE_BUCKET variable is not. Set it to the bootstrap's state_bucket_name output."
  exit 1
fi

echo "run=true" >>"$GITHUB_OUTPUT"
echo "Planning infra/envs/demo against state bucket $TF_STATE_BUCKET."
