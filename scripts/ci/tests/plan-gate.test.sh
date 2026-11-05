#!/usr/bin/env bash
# Tests for scripts/ci/plan-gate.sh, the gate that decides whether infra.yml's plan job runs on a pull request.
# Each case builds a throwaway git repository, so the gate's real git diff is exercised.
# Usage: scripts/ci/tests/plan-gate.test.sh
set -uo pipefail
gate="$(cd "$(dirname "$0")/.." && pwd)/plan-gate.sh"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
failures=0

# repo <changed file>: a repository with a base commit and a head commit that touches the given file.
repo() {
  local dir="$work/repo-$RANDOM$RANDOM"
  git init -q "$dir"
  git -C "$dir" -c user.name=t -c user.email=t@example.com commit -q --allow-empty -m base
  mkdir -p "$dir/$(dirname "$1")"
  echo change >"$dir/$1"
  git -C "$dir" add -A
  git -C "$dir" -c user.name=t -c user.email=t@example.com commit -q -m head
  echo "$dir"
}

# check <name> <changed file> <role arn> <state bucket> <expected exit> <expected run> <expected message>
check() {
  local name=$1 dir out stdout status
  dir=$(repo "$2")
  out="$work/$name.out"
  : >"$out"
  stdout=$(cd "$dir" && AWS_ROLE_ARN=$3 TF_STATE_BUCKET=$4 GITHUB_OUTPUT=$out "$gate" HEAD~1 HEAD 2>&1)
  status=$?
  if [ "$status" != "$5" ]; then
    echo "FAIL $name: exit $status, expected $5"; failures=$((failures + 1)); return
  fi
  if [ -n "$6" ] && ! grep -qx "run=$6" "$out"; then
    echo "FAIL $name: expected run=$6, got: $(cat "$out")"; failures=$((failures + 1)); return
  fi
  if [ -z "$6" ] && [ -s "$out" ]; then
    echo "FAIL $name: expected no output, got: $(cat "$out")"; failures=$((failures + 1)); return
  fi
  if ! grep -qF "$7" <<<"$stdout"; then
    echo "FAIL $name: expected message '$7', got: $stdout"; failures=$((failures + 1)); return
  fi
  echo "ok   $name"
}

role=arn:aws:iam::123456789012:role/rag-agent-studio-github-deploy
bucket=rag-agent-studio-tfstate-123456789012

check runs_when_the_secret_is_set_and_infra_changed infra/modules/network/main.tf "$role" "$bucket" 0 true "Planning infra/envs/demo"
check runs_when_the_infra_workflow_changed .github/workflows/infra.yml "$role" "$bucket" 0 true "Planning infra/envs/demo"
check skips_without_the_secret infra/modules/network/main.tf "" "$bucket" 0 false "::notice title=terraform plan skipped::The AWS_DEPLOY_ROLE_ARN secret is not configured"
check skips_when_no_infrastructure_changed backend/app/main.py "$role" "$bucket" 0 false "::notice title=terraform plan skipped::This pull request changes nothing under infra/"
check fails_when_the_state_bucket_is_missing infra/envs/demo/main.tf "$role" "" 1 "" "::error title=terraform plan misconfigured::AWS_DEPLOY_ROLE_ARN is set but the TF_STATE_BUCKET variable is not"

# A base commit that does not exist must fail the job rather than silently skip the plan.
dir=$(repo infra/envs/demo/main.tf)
if (cd "$dir" && AWS_ROLE_ARN=$role TF_STATE_BUCKET=$bucket GITHUB_OUTPUT=$work/missing.out "$gate" 0000000000000000000000000000000000000000 HEAD >/dev/null 2>&1); then
  echo "FAIL fails_when_the_base_commit_is_unknown: exit 0"; failures=$((failures + 1))
else
  echo "ok   fails_when_the_base_commit_is_unknown"
fi

# Missing arguments are a usage error.
if (AWS_ROLE_ARN=$role GITHUB_OUTPUT=$work/usage.out "$gate" >/dev/null 2>&1); then
  echo "FAIL rejects_missing_arguments: exit 0"; failures=$((failures + 1))
else
  echo "ok   rejects_missing_arguments"
fi

exit $((failures > 0))
