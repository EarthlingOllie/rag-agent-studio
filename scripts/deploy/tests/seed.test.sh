#!/usr/bin/env bash
# Tests for scripts/deploy/seed.sh, the seed workflow's run (ticket 10-05): the demo data seeded into the deployed demo
# environment by a one-off ECS task. terraform and aws are stubs (tests/stubs) that log every call and answer as each
# case says; nothing calls AWS.
# Usage: scripts/deploy/tests/seed.test.sh
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
seed="$here/../seed.sh"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
failures=0

fail() { echo "FAIL $1: $2"; failures=$((failures + 1)); }

task_arn=arn:aws:ecs:eu-west-2:123456789012:task/studio-demo-ecs/0123456789abcdef

# What `terraform output -json deploy` prints after a deploy that has the seed task.
deploy_json() {
  jq -n '{
    image_tag: "0123abc",
    cluster_name: "studio-demo-ecs",
    seed_task: {
      task_definition_arn: "arn:aws:ecs:eu-west-2:123456789012:task-definition/studio-demo-ecs-seed:7",
      container_name: "seed",
      subnet_ids: ["subnet-0ccccccccccccccc3", "subnet-0ddddddddddddddd4"],
      security_group_id: "sg-0seed00000000001",
      log_group_name: "/ecs/studio-demo-ecs/seed",
      log_stream_prefix: "seed"
    },
    cloudfront_url: "https://d111111abcdef8.cloudfront.net"
  }'
}

# run <case> [args...] [-- VAR=value...]: runs seed.sh in a fresh case directory; sets $status, $out, $calls.
run() {
  local name=$1 args=() vars=()
  shift
  while [ $# -gt 0 ] && [ "$1" != -- ]; do args+=("$1"); shift; done
  [ "${1:-}" = -- ] && { shift; vars=("$@"); }
  dir="$work/$name"
  mkdir -p "$dir"
  : >"$dir/calls"
  [ -f "$dir/deploy.json" ] || deploy_json >"$dir/deploy.json"
  out=$(env PATH="$here/stubs:$PATH" STUB_CALLS="$dir/calls" STUB_DEPLOY_JSON="$dir/deploy.json" \
    TF_STATE_BUCKET=rag-agent-studio-tfstate-123456789012 AWS_REGION=eu-west-2 DEPLOY_ROOT=/repo/infra/envs/demo \
    GITHUB_STEP_SUMMARY="$dir/summary.md" "${vars[@]}" "$seed" "${args[@]}" 2>&1)
  status=$?
  calls=$(cat "$dir/calls")
}

expect_status() { if [ "$status" != "$2" ]; then fail "$1" "exit $status, expected $2. Output: $out"; return 1; fi; }
expect_output() { if ! grep -qF -- "$2" <<<"$out"; then fail "$1" "expected '$2' in: $out"; return 1; fi; }
expect_call() { if ! grep -qxF -- "$2" <<<"$calls"; then fail "$1" "expected the call '$2' in: $calls"; return 1; fi; }
never() { if grep -qE -- "$2" <<<"$calls"; then fail "$1" "unexpected call matching '$2'"; return 1; fi; }

init_call='terraform -chdir=/repo/infra/envs/demo init -input=false -backend-config=bucket=rag-agent-studio-tfstate-123456789012 -backend-config=region=eu-west-2'
network='awsvpcConfiguration={subnets=[subnet-0ccccccccccccccc3,subnet-0ddddddddddddddd4],securityGroups=[sg-0seed00000000001],assignPublicIp=DISABLED}'
seed_run_task="aws ecs run-task --cluster studio-demo-ecs --task-definition arn:aws:ecs:eu-west-2:123456789012:task-definition/studio-demo-ecs-seed:7 --launch-type FARGATE --started-by seed-demo --network-configuration $network --query tasks[0].taskArn --output text"

# --- The happy path: read the deployed environment, run the seed task, wait, check it, show its output ---------------

name=runs_the_seed_as_a_one_off_ecs_task_and_prints_its_output
run "$name" -- STUB_LOG_MESSAGES=$'Seeded the demo Organisation \'Northwind\'.\tStudio: https://d111111abcdef8.cloudfront.net'
ok=1
expect_status $name 0 || ok=0
expected_calls="$init_call
terraform -chdir=/repo/infra/envs/demo output -json deploy
$seed_run_task
aws ecs wait tasks-stopped --cluster studio-demo-ecs --tasks $task_arn
aws ecs describe-tasks --cluster studio-demo-ecs --tasks $task_arn --query tasks[0].containers[?name==\`seed\`].exitCode | [0] --output text
aws logs get-log-events --log-group-name /ecs/studio-demo-ecs/seed --log-stream-name seed/seed/0123456789abcdef --start-from-head --query events[].message --output text"
[ "$calls" = "$expected_calls" ] || { fail $name "calls were:
$calls"; ok=0; }
expect_output $name "Seeded the demo Organisation 'Northwind'." || ok=0
expect_output $name "Studio: https://d111111abcdef8.cloudfront.net" || ok=0
expect_output $name "The demo environment is seeded: https://d111111abcdef8.cloudfront.net" || ok=0
grep -qF "Seeded the demo Organisation 'Northwind'." "$work/$name/summary.md" || { fail $name "summary: $(cat "$work/$name/summary.md")"; ok=0; }
[ $ok = 1 ] && echo "ok   $name"

name=never_applies_or_changes_the_infrastructure
ok=1
never $name '^terraform -chdir=[^ ]+ (apply|destroy|import|state|taint)' || ok=0
never $name '^aws ecs (update-service|register-task-definition|create|delete)' || ok=0
[ $ok = 1 ] && echo "ok   $name"

# --- Idempotent: a second run asks for exactly the same seed, which completes what is there and duplicates nothing ----

name=running_it_again_runs_the_same_non_destructive_seed
first=$(grep 'ecs run-task' "$work/runs_the_seed_as_a_one_off_ecs_task_and_prints_its_output/calls")
run "$name"
ok=1
expect_status $name 0 || ok=0
[ "$(grep 'ecs run-task' <<<"$calls")" = "$first" ] || { fail $name "second run-task differed: $(grep 'ecs run-task' <<<"$calls")"; ok=0; }
never $name 'overrides|--reset' || ok=0
[ $ok = 1 ] && echo "ok   $name"

# --- --reset: erase the demo Organisation (only that one) and seed it again --------------------------------------------

name=reset_overrides_the_command_with_seed_reset
run "$name" --reset
ok=1
expect_status $name 0 || ok=0
# shellcheck disable=SC2016 # The JSON is literal.
expect_call $name "aws ecs run-task --cluster studio-demo-ecs --task-definition arn:aws:ecs:eu-west-2:123456789012:task-definition/studio-demo-ecs-seed:7 --launch-type FARGATE --started-by seed-demo-reset --network-configuration $network --overrides {\"containerOverrides\":[{\"name\":\"seed\",\"command\":[\"python\",\"-m\",\"app.seed\",\"--reset\"]}]} --query tasks[0].taskArn --output text" || ok=0
[ $ok = 1 ] && echo "ok   $name"

# --- Waiting: a long seed is waited for in rounds; one that never stops fails the run --------------------------------

name=keeps_waiting_while_the_seed_runs
run "$name" -- STUB_TASK_STOPS_AFTER_WAITS=3 SEED_WAIT_ROUNDS=4
ok=1
expect_status $name 0 || ok=0
[ "$(grep -c 'ecs wait tasks-stopped' <<<"$calls")" = 3 ] || { fail $name "waited $(grep -c 'ecs wait tasks-stopped' <<<"$calls") times"; ok=0; }
[ $ok = 1 ] && echo "ok   $name"

name=a_seed_that_never_stops_fails_the_run
run "$name" -- STUB_TASK_STOPS_AFTER_WAITS=9 SEED_WAIT_ROUNDS=2
ok=1
expect_status $name 1 || ok=0
expect_output $name "The seed task is still running after 2 waits ($task_arn)" || ok=0
never $name '^aws ecs describe-tasks' || ok=0
[ $ok = 1 ] && echo "ok   $name"

# --- Failures stop the run with the reason ---------------------------------------------------------------------------

name=a_failed_seed_fails_the_run_and_shows_its_output
run "$name" -- STUB_TASK_EXIT_CODE=1 STUB_LOG_MESSAGES='Seed failed: A demo Document failed ingestion'
ok=1
expect_status $name 1 || ok=0
expect_output $name "Seed task exited 1 ($task_arn)" || ok=0
expect_output $name "Seed failed: A demo Document failed ingestion" || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=a_seed_task_that_never_ran_fails_the_run
run "$name" -- STUB_TASK_EXIT_CODE=None
ok=1
expect_status $name 1 || ok=0
expect_output $name "Seed task exited None" || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=a_seed_task_that_cannot_start_fails_the_run
run "$name" -- STUB_RUN_TASK_ARN=None
ok=1
expect_status $name 1 || ok=0
expect_output $name "The seed task did not start (None)" || ok=0
never $name '^aws ecs wait' || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=missing_logs_do_not_hide_a_successful_seed
run "$name" -- STUB_LOGS_EXIT=254
ok=1
expect_status $name 0 || ok=0
expect_output $name "Could not read the seed task's log" || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=an_environment_deployed_without_the_seed_task_asks_for_a_deploy
dir="$work/$name"; mkdir -p "$dir"
deploy_json | jq 'del(.seed_task)' >"$dir/deploy.json"
run "$name"
ok=1
expect_status $name 1 || ok=0
expect_output $name "has no seed task: run the deploy workflow first" || ok=0
never $name '^aws' || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=an_environment_that_is_not_deployed_asks_for_a_deploy
run "$name" -- STUB_TF_OUTPUT_EXIT=1
ok=1
expect_status $name 1 || ok=0
expect_output $name "The demo environment is not deployed" || ok=0
never $name '^aws' || ok=0
[ $ok = 1 ] && echo "ok   $name"

# --- Nothing is touched when the inputs are wrong --------------------------------------------------------------------

name=requires_the_state_bucket
run "$name" -- TF_STATE_BUCKET=
ok=1
expect_status $name 2 || ok=0
expect_output $name "TF_STATE_BUCKET" || ok=0
[ -z "$calls" ] || { fail $name "calls were made: $calls"; ok=0; }
[ $ok = 1 ] && echo "ok   $name"

name=requires_the_region
run "$name" -- AWS_REGION=
ok=1
expect_status $name 2 || ok=0
expect_output $name "AWS_REGION" || ok=0
[ -z "$calls" ] || { fail $name "calls were made: $calls"; ok=0; }
[ $ok = 1 ] && echo "ok   $name"

for bad in "--wipe" "--reset extra" "reset"; do
  name="rejects_the_arguments_'$bad'"
  # shellcheck disable=SC2086 # Split on purpose: each case is a list of arguments.
  run "$name" $bad
  ok=1
  expect_status "$name" 2 || ok=0
  expect_output "$name" "usage:" || ok=0
  [ -z "$calls" ] || { fail "$name" "calls were made: $calls"; ok=0; }
  [ $ok = 1 ] && echo "ok   $name"
done

name=rejects_a_wait_that_is_not_a_positive_number
run "$name" -- SEED_WAIT_ROUNDS=0
ok=1
expect_status $name 2 || ok=0
expect_output $name "SEED_WAIT_ROUNDS" || ok=0
[ -z "$calls" ] || { fail $name "calls were made: $calls"; ok=0; }
[ $ok = 1 ] && echo "ok   $name"

exit $((failures > 0))
