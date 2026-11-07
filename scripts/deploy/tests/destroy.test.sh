#!/usr/bin/env bash
# Tests for scripts/deploy/destroy.sh, the destroy workflow's only step (spec 09 story 27). terraform is a stub
# (tests/stubs) that logs every call; nothing calls AWS.
# Usage: scripts/deploy/tests/destroy.test.sh
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
destroy="$here/../destroy.sh"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
failures=0

# check <name> <expected exit> <expected message> <expected calls (one per line, empty for none)> <confirmation> [VAR=value...]
check() {
  local name=$1 expected=$2 message=$3 expected_calls=$4 confirmation=$5 out status calls
  shift 5
  : >"$work/$name.calls"
  out=$(env PATH="$here/stubs:$PATH" STUB_CALLS="$work/$name.calls" TF_STATE_BUCKET=rag-agent-studio-tfstate-123456789012 \
    AWS_REGION=eu-west-2 DEPLOY_ROOT=/repo/infra/envs/demo "$@" "$destroy" "$confirmation" 2>&1)
  status=$?
  calls=$(cat "$work/$name.calls")
  if [ "$status" != "$expected" ]; then echo "FAIL $name: exit $status, expected $expected. Output: $out"; failures=$((failures + 1)); return; fi
  if ! grep -qF -- "$message" <<<"$out"; then echo "FAIL $name: expected '$message' in: $out"; failures=$((failures + 1)); return; fi
  if [ "$calls" != "$expected_calls" ]; then echo "FAIL $name: calls were: $calls"; failures=$((failures + 1)); return; fi
  echo "ok   $name"
}

destroyed="terraform -chdir=/repo/infra/envs/demo init -input=false -backend-config=bucket=rag-agent-studio-tfstate-123456789012 -backend-config=region=eu-west-2
terraform -chdir=/repo/infra/envs/demo destroy -input=false -auto-approve"

check destroys_the_demo_when_the_confirmation_is_typed_exactly 0 "The demo environment is destroyed" "$destroyed" "destroy demo"
check refuses_without_a_confirmation 1 "Type exactly 'destroy demo'" "" ""
check refuses_a_confirmation_that_is_nearly_right 1 "Type exactly 'destroy demo'" "" "Destroy demo"
check refuses_a_confirmation_with_extra_text 1 "Type exactly 'destroy demo'" "" "destroy demo now"
check refuses_the_environment_name_alone 1 "Type exactly 'destroy demo'" "" "demo"
check requires_the_state_bucket 2 "TF_STATE_BUCKET" "" "destroy demo" TF_STATE_BUCKET=
check a_failed_destroy_fails_the_run 1 "" "$destroyed" "destroy demo" STUB_TF_DESTROY_EXIT=1

if out=$("$destroy" 2>&1); then echo "FAIL rejects_missing_arguments: exit 0"; failures=$((failures + 1))
elif grep -qF "usage:" <<<"$out"; then echo "ok   rejects_missing_arguments"
else echo "FAIL rejects_missing_arguments: $out"; failures=$((failures + 1)); fi

exit $((failures > 0))
