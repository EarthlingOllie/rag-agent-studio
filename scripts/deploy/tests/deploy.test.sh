#!/usr/bin/env bash
# Tests for scripts/deploy/deploy.sh, the deploy workflow's apply run (spec 09 stories 25, 26 and 32).
# terraform, aws and docker are stubs (tests/stubs) that log every call and answer as each case says; nothing calls
# AWS. sleep is stubbed too (tests/stubs-clock), so the wait for protected tasks (ticket 22-06) passes in no time and
# each sleep is logged. The smoke check runs for real, with curl, against a local HTTP server (fake_site.py) standing in for CloudFront.
# Usage: scripts/deploy/tests/deploy.test.sh
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
deploy="$here/../deploy.sh"
work=$(mktemp -d)
site_pid=""
trap '[ -z "$site_pid" ] || kill "$site_pid" 2>/dev/null; rm -rf "$work"' EXIT
failures=0

fail() { echo "FAIL $1: $2"; failures=$((failures + 1)); }

# A healthy deployed site.
jq -n '{
  "/api/health": {status: 200, headers: {"Content-Type": "application/json"}, body: "{\"status\":\"ok\",\"checks\":{\"database\":\"ok\",\"redis\":\"ok\"}}"},
  "/": {status: 200, headers: {"Content-Type": "text/html"}, body: "<!doctype html><html><body><div id=\"root\"></div></body></html>"},
  "/widget/a/smoke-check": {status: 404, headers: {"Content-Type": "text/html", "Content-Security-Policy": "frame-ancestors *"}, body: "gone"}
}' >"$work/site.json"
python3 -I "$here/fake_site.py" "$work/site.json" >"$work/site.port" 2>/dev/null &
site_pid=$!
for _ in $(seq 100); do [ -s "$work/site.port" ] && break; sleep 0.05; done
site_url="http://127.0.0.1:$(cat "$work/site.port")"

# The frontend builds the workflow uploads: the Studio's and the widget's dist folders.
mkdir -p "$work/studio/assets" "$work/widget/widget/assets"
echo '<div id="root"></div>' >"$work/studio/index.html"
echo 'studio' >"$work/studio/assets/index-abc123.js"
echo 'loader' >"$work/widget/embed.js"
echo 'widget' >"$work/widget/widget/assets/widget.js"
echo 'chunk' >"$work/widget/widget/assets/chunk-def456.js"
# The demo pages (ticket 10-03) and the attack panel (ticket 10-04), static HTML uploaded under /demo/.
mkdir -p "$work/demo"
for page in index inline budget attacks; do echo "<h1>$page</h1>" >"$work/demo/$page.html"; done

deploy_json() {
  jq -n --arg url "$1" '{
    image_tag: "0123abc",
    cluster_name: "studio-demo-ecs",
    services: {api: "studio-demo-ecs-api", "worker-general": "studio-demo-ecs-worker-general", "worker-runs": "studio-demo-ecs-worker-runs", beat: "studio-demo-ecs-beat"},
    task_definition_arns: {
      api: "arn:aws:ecs:eu-west-2:123456789012:task-definition/studio-demo-ecs-api:7",
      beat: "arn:aws:ecs:eu-west-2:123456789012:task-definition/studio-demo-ecs-beat:7",
      "worker-general": "arn:aws:ecs:eu-west-2:123456789012:task-definition/studio-demo-ecs-worker-general:7",
      "worker-runs": "arn:aws:ecs:eu-west-2:123456789012:task-definition/studio-demo-ecs-worker-runs:7"
    },
    migration_task: {
      task_definition_arn: "arn:aws:ecs:eu-west-2:123456789012:task-definition/studio-demo-ecs-migrate:7",
      container_name: "migrate",
      subnet_ids: ["subnet-0ccccccccccccccc3", "subnet-0ddddddddddddddd4"],
      security_group_id: "sg-0migrate000000001"
    },
    static_bucket_name: "studio-demo-static-123456789012",
    cloudfront_distribution_id: "E2EXAMPLE0ABCD",
    cloudfront_url: $url
  }'
}

# run <case> <tag> [VAR=value...]: runs deploy.sh in a fresh case directory; sets $status, $out, $calls, $dir.
# A wait_minutes=N prefix passes N as deploy.sh's second argument (the wait for protected tasks).
run() {
  local name=$1 tag=$2
  shift 2
  dir="$work/$name"
  mkdir -p "$dir"
  : >"$dir/calls"
  deploy_json "$site_url" >"$dir/deploy.json"
  out=$(env PATH="$here/stubs:$here/stubs-clock:$PATH" STUB_CALLS="$dir/calls" STUB_DEPLOY_JSON="$dir/deploy.json" STUB_UPLOADED="$dir/uploaded" \
    TF_STATE_BUCKET=rag-agent-studio-tfstate-123456789012 AWS_REGION=eu-west-2 \
    STUDIO_DIST="$work/studio" WIDGET_DIST="$work/widget" DEMO_DIST="$work/demo" SMOKE_ATTEMPTS=1 SMOKE_DELAY_SECONDS=0 \
    GITHUB_STEP_SUMMARY="$dir/summary.md" "$@" "$deploy" "$tag" ${wait_minutes:+"$wait_minutes"} 2>&1)
  status=$?
  calls=$(cat "$dir/calls")
}

# line <pattern>: the line number of the first call matching the pattern (empty if none).
line() { grep -n -m1 -E -- "$1" <<<"$calls" | cut -d: -f1; }

# before <case> <first pattern> <second pattern>: the first call happens, and before the second.
before() {
  local a b
  a=$(line "$2"); b=$(line "$3")
  if [ -n "$a" ] && [ -n "$b" ] && [ "$a" -lt "$b" ]; then return 0; fi
  fail "$1" "expected '$2' (line ${a:-none}) before '$3' (line ${b:-none})"
  return 1
}

# never <case> <pattern>: no call matches.
never() { if grep -qE -- "$2" <<<"$calls"; then fail "$1" "unexpected call matching '$2'"; return 1; fi; }

expect_status() { if [ "$status" != "$2" ]; then fail "$1" "exit $status, expected $2. Output: $out"; return 1; fi; }
expect_output() { if ! grep -qF -- "$2" <<<"$out"; then fail "$1" "expected '$2' in: $out"; return 1; fi; }

# --- The happy path: apply at the tag, migrate, roll, upload, invalidate, smoke check --------------------------------

name=deploys_in_order_at_the_given_tag
run "$name" 0123abc STUB_IMAGE_IN_ECR=0
ok=1
expect_status $name 0 || ok=0
before $name '^terraform -chdir=.*init -input=false -backend-config=bucket=rag-agent-studio-tfstate-123456789012 -backend-config=region=eu-west-2' '^terraform .* apply ' || ok=0
before $name '^terraform .* apply .*-target=module.ecr' '^aws ecr describe-images --repository-name rag-agent-studio/api --image-ids imageTag=0123abc' || ok=0
before $name '^aws ecr describe-images' '^terraform .* apply -input=false -auto-approve -var=image_tag=0123abc$' || ok=0
before $name '^terraform .* apply -input=false -auto-approve -var=image_tag=0123abc$' '^aws ecs run-task' || ok=0
before $name '^aws ecs run-task' '^aws ecs wait tasks-stopped --cluster studio-demo-ecs --tasks arn:aws:ecs:eu-west-2:123456789012:task/studio-demo-ecs/0123456789abcdef' || ok=0
before $name '^aws ecs wait tasks-stopped' '^aws ecs describe-tasks' || ok=0
before $name '^aws ecs describe-tasks' '^aws ecs update-service' || ok=0
before $name '^aws ecs update-service .*--service studio-demo-ecs-worker-runs ' '^aws ecs wait services-stable --cluster studio-demo-ecs --services studio-demo-ecs-api$' || ok=0
before $name '^aws ecs wait services-stable' '^aws s3 sync' || ok=0
before $name '^aws s3 sync' '^aws cloudfront create-invalidation' || ok=0
before $name '^aws cloudfront create-invalidation' '^aws cloudfront wait invalidation-completed --distribution-id E2EXAMPLE0ABCD --id I2J0I21PCUYOIK' || ok=0
expect_output $name "Smoke check passed: $site_url" || ok=0
never $name '^docker' || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=runs_the_migration_task_in_the_private_subnets
ok=1
grep -qxF 'aws ecs run-task --cluster studio-demo-ecs --task-definition arn:aws:ecs:eu-west-2:123456789012:task-definition/studio-demo-ecs-migrate:7 --launch-type FARGATE --started-by deploy-0123abc --network-configuration awsvpcConfiguration={subnets=[subnet-0ccccccccccccccc3,subnet-0ddddddddddddddd4],securityGroups=[sg-0migrate000000001],assignPublicIp=DISABLED} --query tasks[0].taskArn --output text' <<<"$calls" || { fail $name "run-task call was: $(grep 'run-task' <<<"$calls")"; ok=0; }
# shellcheck disable=SC2016 # The backticks are a JMESPath literal.
grep -qxF 'aws ecs describe-tasks --cluster studio-demo-ecs --tasks arn:aws:ecs:eu-west-2:123456789012:task/studio-demo-ecs/0123456789abcdef --query tasks[0].containers[?name==`migrate`].exitCode | [0] --output text' <<<"$calls" || { fail $name "describe-tasks call was: $(grep 'describe-tasks' <<<"$calls")"; ok=0; }
[ $ok = 1 ] && echo "ok   $name"

name=rolls_the_api_both_worker_pools_and_beat_onto_their_new_task_definitions
ok=1
rolled=$(grep -c '^aws ecs update-service' <<<"$calls")
[ "$rolled" = 4 ] || { fail $name "expected 4 update-service calls, got $rolled"; ok=0; }
for svc in api beat worker-general worker-runs; do
  grep -qxF "aws ecs update-service --cluster studio-demo-ecs --service studio-demo-ecs-$svc --task-definition arn:aws:ecs:eu-west-2:123456789012:task-definition/studio-demo-ecs-$svc:7 --query service.serviceName --output text" <<<"$calls" || { fail $name "no update-service for $svc"; ok=0; }
done
[ $ok = 1 ] && echo "ok   $name"

# Ticket 22-04 (spec 22 story 26): every service is rolled before any wait, and each is reported stable on its own.
name=reports_each_service_as_stable
ok=1
waits=$(grep '^aws ecs wait services-stable' <<<"$calls")
[ "$waits" = "aws ecs wait services-stable --cluster studio-demo-ecs --services studio-demo-ecs-api
aws ecs wait services-stable --cluster studio-demo-ecs --services studio-demo-ecs-beat
aws ecs wait services-stable --cluster studio-demo-ecs --services studio-demo-ecs-worker-general
aws ecs wait services-stable --cluster studio-demo-ecs --services studio-demo-ecs-worker-runs" ] || { fail $name "waits were: $waits"; ok=0; }
for svc in api beat worker-general worker-runs; do
  expect_output $name "studio-demo-ecs-$svc is stable" || ok=0
done
[ $ok = 1 ] && echo "ok   $name"

name=uploads_the_studio_widget_and_demo_pages_and_invalidates_html_and_the_loader
ok=1
uploaded=$(cd "$work/deploys_in_order_at_the_given_tag/uploaded" && find . -type f | sort | tr '\n' ' ')
[ "$uploaded" = "./assets/index-abc123.js ./demo/attacks.html ./demo/budget.html ./demo/index.html ./demo/inline.html ./embed.js ./index.html ./widget/assets/chunk-def456.js ./widget/assets/widget.js " ] || { fail $name "uploaded: $uploaded"; ok=0; }
grep -qE '^aws s3 sync .* s3://studio-demo-static-123456789012 --delete --cache-control public,max-age=31536000,immutable --exclude index.html --exclude embed.js --exclude widget/assets/widget.js --exclude demo/attacks.html --exclude demo/budget.html --exclude demo/index.html --exclude demo/inline.html$' <<<"$calls" || { fail $name "sync was: $(grep 's3 sync' <<<"$calls")"; ok=0; }
for f in index.html embed.js widget/assets/widget.js demo/attacks.html demo/budget.html demo/index.html demo/inline.html; do
  grep -qE "^aws s3 cp .*/$f s3://studio-demo-static-123456789012/$f --cache-control no-cache$" <<<"$calls" || { fail $name "no no-cache upload of $f"; ok=0; }
done
grep -qxF 'aws cloudfront create-invalidation --distribution-id E2EXAMPLE0ABCD --paths / /index.html /embed.js /widget/assets/widget.js /demo/* --query Invalidation.Id --output text' <<<"$calls" || { fail $name "invalidation was: $(grep 'create-invalidation' <<<"$calls")"; ok=0; }
[ $ok = 1 ] && echo "ok   $name"

name=prints_the_cloudfront_url_in_the_job_summary
summary=$(cat "$work/deploys_in_order_at_the_given_tag/summary.md")
if grep -qF "$site_url" <<<"$summary" && grep -qF '0123abc' <<<"$summary"; then echo "ok   $name"; else fail $name "summary: $summary"; fi

# --- Ticket 22-06: the roll waits for running jobs (protected old worker tasks), then clears their protection --------

name=finds_old_worker_tasks_and_asks_whether_they_are_protected
run "$name" 0123abc STUB_IMAGE_IN_ECR=0 STUB_OLD_TASKS=1
ok=1
expect_status $name 0 || ok=0
for svc in worker-general worker-runs; do
  grep -qxF "aws ecs list-tasks --cluster studio-demo-ecs --service-name studio-demo-ecs-$svc --desired-status RUNNING --query taskArns --output text" <<<"$calls" || { fail $name "no list-tasks for $svc"; ok=0; }
  # shellcheck disable=SC2016 # The backticks are a JMESPath literal.
  grep -qxF "aws ecs describe-tasks --cluster studio-demo-ecs --tasks arn:aws:ecs:eu-west-2:123456789012:task/studio-demo-ecs/studio-demo-ecs-$svc-old --query tasks[?taskDefinitionArn!=\`arn:aws:ecs:eu-west-2:123456789012:task-definition/studio-demo-ecs-$svc:7\`].taskArn --output text" <<<"$calls" || { fail $name "no old-task lookup for $svc: $(grep 'describe-tasks' <<<"$calls")"; ok=0; }
  grep -qxF "aws ecs get-task-protection --cluster studio-demo-ecs --tasks arn:aws:ecs:eu-west-2:123456789012:task/studio-demo-ecs/studio-demo-ecs-$svc-old --query protectedTasks[?protectionEnabled].taskArn --output text" <<<"$calls" || { fail $name "no protection lookup for $svc"; ok=0; }
done
never $name '^aws ecs (list-tasks|get-task-protection) .*studio-demo-ecs-(api|beat)' || ok=0
before $name '^aws ecs update-service .*--service studio-demo-ecs-worker-runs ' '^aws ecs list-tasks' || ok=0
never $name '^sleep 30' || ok=0
never $name '^aws ecs update-task-protection' || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=waits_while_old_worker_tasks_are_protected_and_lets_the_roll_finish_when_their_jobs_end
run "$name" 0123abc STUB_IMAGE_IN_ECR=0 STUB_OLD_TASKS=1 STUB_PROTECTED_IN=worker-runs STUB_PROTECTED_CHECKS=3
ok=1
expect_status $name 0 || ok=0
sleeps=$(grep -c '^sleep 30$' <<<"$calls")
[ "$sleeps" = 3 ] || { fail $name "expected 3 waits of 30 s, got $sleeps"; ok=0; }
expect_output $name "Waiting for 1 old worker task still running a job (0 of 30 minutes)" || ok=0
never $name '^aws ecs update-task-protection' || ok=0
last_check=$(grep -n '^aws ecs get-task-protection' <<<"$calls" | tail -1 | cut -d: -f1)
first_wait=$(line '^aws ecs wait services-stable')
[ -n "$first_wait" ] && [ "$last_check" -lt "$first_wait" ] || { fail $name "the services were waited on before the protected tasks finished"; ok=0; }
expect_output $name "studio-demo-ecs-worker-runs is stable" || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=clears_protection_on_old_tasks_after_30_minutes_and_lets_the_roll_finish
run "$name" 0123abc STUB_IMAGE_IN_ECR=0 STUB_OLD_TASKS=1 STUB_PROTECTED_IN=worker-runs
ok=1
expect_status $name 0 || ok=0
sleeps=$(grep -c '^sleep 30$' <<<"$calls")
[ "$sleeps" = 60 ] || { fail $name "expected 60 waits of 30 s (30 minutes), got $sleeps"; ok=0; }
grep -qxF 'aws ecs update-task-protection --cluster studio-demo-ecs --tasks arn:aws:ecs:eu-west-2:123456789012:task/studio-demo-ecs/studio-demo-ecs-worker-runs-old --no-protection-enabled --query failures --output text' <<<"$calls" || { fail $name "protection was not cleared: $(grep 'update-task-protection' <<<"$calls")"; ok=0; }
before $name '^sleep 30' '^aws ecs update-task-protection' || ok=0
before $name '^aws ecs update-task-protection' '^aws ecs wait services-stable' || ok=0
expect_output $name "Clearing scale-in protection on 1 old worker task after 30 minutes" || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=the_wait_for_protected_tasks_is_an_argument
wait_minutes=5 run "$name" 0123abc STUB_IMAGE_IN_ECR=0 STUB_OLD_TASKS=1 STUB_PROTECTED_IN=worker-
ok=1
expect_status $name 0 || ok=0
sleeps=$(grep -c '^sleep 30$' <<<"$calls")
[ "$sleeps" = 10 ] || { fail $name "expected 10 waits of 30 s (5 minutes), got $sleeps"; ok=0; }
grep -qxF 'aws ecs update-task-protection --cluster studio-demo-ecs --tasks arn:aws:ecs:eu-west-2:123456789012:task/studio-demo-ecs/studio-demo-ecs-worker-general-old arn:aws:ecs:eu-west-2:123456789012:task/studio-demo-ecs/studio-demo-ecs-worker-runs-old --no-protection-enabled --query failures --output text' <<<"$calls" || { fail $name "protection was not cleared on both pools: $(grep 'update-task-protection' <<<"$calls")"; ok=0; }
expect_output $name "Clearing scale-in protection on 2 old worker tasks after 5 minutes" || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=no_wait_clears_protection_at_once
wait_minutes=0 run "$name" 0123abc STUB_IMAGE_IN_ECR=0 STUB_OLD_TASKS=1 STUB_PROTECTED_IN=worker-runs
ok=1
expect_status $name 0 || ok=0
never $name '^sleep 30' || ok=0
grep -q '^aws ecs update-task-protection' <<<"$calls" || { fail $name "protection was not cleared"; ok=0; }
[ $ok = 1 ] && echo "ok   $name"

name=a_failure_to_clear_protection_stops_the_deploy
wait_minutes=0 run "$name" 0123abc STUB_IMAGE_IN_ECR=0 STUB_OLD_TASKS=1 STUB_PROTECTED_IN=worker-runs STUB_CLEAR_FAILURES=MISSING
ok=1
expect_status $name 1 || ok=0
expect_output $name "Could not clear scale-in protection" || ok=0
never $name '^aws ecs wait services-stable' || ok=0
[ $ok = 1 ] && echo "ok   $name"

for bad in abc -1 1.5; do
  name="rejects_the_wait_'$bad'"
  wait_minutes=$bad run "$name" 0123abc STUB_IMAGE_IN_ECR=0
  ok=1
  expect_status "$name" 2 || ok=0
  [ -z "$calls" ] || { fail "$name" "calls were made: $calls"; ok=0; }
  [ $ok = 1 ] && echo "ok   $name"
done

# --- Images: a tag already in ECR is deployed as is; otherwise the locally built images are pushed first --------------

name=pushes_locally_built_images_when_the_tag_is_not_in_ecr
run "$name" 0123abc STUB_IMAGE_IN_ECR=254 STUB_LOCAL_IMAGES=1
ok=1
expect_status $name 0 || ok=0
# The password is piped from aws into docker login, so the two log in either order; both precede the pushes.
before $name '^aws ecr get-login-password --region eu-west-2' '^docker push' || ok=0
before $name '^docker login --username AWS --password-stdin 123456789012.dkr.ecr.eu-west-2.amazonaws.com' '^docker push' || ok=0
for image in api studio; do
  grep -qxF "docker tag rag-agent-studio/$image:0123abc 123456789012.dkr.ecr.eu-west-2.amazonaws.com/rag-agent-studio/$image:0123abc" <<<"$calls" || { fail $name "no tag of $image"; ok=0; }
  grep -qxF "docker push 123456789012.dkr.ecr.eu-west-2.amazonaws.com/rag-agent-studio/$image:0123abc" <<<"$calls" || { fail $name "no push of $image"; ok=0; }
done
before $name '^docker push .*/rag-agent-studio/api:0123abc' '^terraform .* apply -input=false -auto-approve -var=image_tag=0123abc$' || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=refuses_to_push_images_that_are_not_arm64
run "$name" 0123abc STUB_IMAGE_IN_ECR=254 STUB_LOCAL_IMAGES=1 STUB_LOCAL_ARCH=amd64
ok=1
expect_status $name 1 || ok=0
expect_output $name "rag-agent-studio/api:0123abc is built for amd64, but the tasks run on arm64" || ok=0
never $name '^docker push' || ok=0
never $name '^terraform .* apply -input=false -auto-approve -var=image_tag' || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=fails_when_the_tag_is_neither_in_ecr_nor_built
run "$name" 0123abc STUB_IMAGE_IN_ECR=254 STUB_LOCAL_IMAGES=0
ok=1
expect_status $name 1 || ok=0
expect_output $name "rag-agent-studio/api:0123abc is not in ECR and was not built here" || ok=0
never $name '^terraform .* apply -input=false -auto-approve -var=image_tag' || ok=0
never $name '^docker push' || ok=0
[ $ok = 1 ] && echo "ok   $name"

# --- Migrations gate the rollout -------------------------------------------------------------------------------------

name=a_failed_migration_stops_before_any_service_rolls
run "$name" 0123abc STUB_IMAGE_IN_ECR=0 STUB_MIGRATION_EXIT_CODE=1
ok=1
expect_status $name 1 || ok=0
expect_output $name "Migration task exited 1" || ok=0
never $name '^aws ecs update-service' || ok=0
never $name '^aws s3' || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=a_migration_that_never_ran_stops_the_deploy
run "$name" 0123abc STUB_IMAGE_IN_ECR=0 STUB_MIGRATION_EXIT_CODE=None
ok=1
expect_status $name 1 || ok=0
expect_output $name "Migration task exited None" || ok=0
never $name '^aws ecs update-service' || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=a_migration_task_that_cannot_start_stops_the_deploy
run "$name" 0123abc STUB_IMAGE_IN_ECR=0 STUB_RUN_TASK_ARN=None
ok=1
expect_status $name 1 || ok=0
expect_output $name "The migration task did not start" || ok=0
never $name '^aws ecs wait tasks-stopped' || ok=0
never $name '^aws ecs update-service' || ok=0
[ $ok = 1 ] && echo "ok   $name"

# --- Failures later on stop the run ----------------------------------------------------------------------------------

name=services_that_do_not_stabilise_fail_before_uploading
run "$name" 0123abc STUB_IMAGE_IN_ECR=0 STUB_STABLE_EXIT=255
ok=1
expect_status $name 1 || ok=0
expect_output $name "did not stabilise" || ok=0
never $name '^aws s3' || ok=0
never $name '^aws cloudfront' || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=a_worker_pool_that_does_not_stabilise_is_named_and_stops_the_deploy
run "$name" 0123abc STUB_IMAGE_IN_ECR=0 STUB_UNSTABLE_SERVICE=studio-demo-ecs-worker-runs
ok=1
expect_status $name 1 || ok=0
expect_output $name "studio-demo-ecs-worker-runs did not stabilise" || ok=0
expect_output $name "studio-demo-ecs-worker-general is stable" || ok=0
never $name '^aws s3' || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=a_failed_apply_stops_the_deploy
run "$name" 0123abc STUB_IMAGE_IN_ECR=0 STUB_TF_APPLY_EXIT=1
ok=1
expect_status $name 1 || ok=0
never $name '^aws ecs' || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=a_failed_smoke_check_fails_the_deploy
dir="$work/$name"; mkdir -p "$dir"
run "$name" 0123abc STUB_IMAGE_IN_ECR=0
deploy_json "http://127.0.0.1:9" >"$dir/deploy.json"
out=$(env PATH="$here/stubs:$PATH" STUB_CALLS="$dir/calls" STUB_DEPLOY_JSON="$dir/deploy.json" STUB_UPLOADED="$dir/uploaded" \
  TF_STATE_BUCKET=rag-agent-studio-tfstate-123456789012 AWS_REGION=eu-west-2 STUB_IMAGE_IN_ECR=0 \
  STUDIO_DIST="$work/studio" WIDGET_DIST="$work/widget" DEMO_DIST="$work/demo" SMOKE_ATTEMPTS=1 SMOKE_DELAY_SECONDS=0 "$deploy" 0123abc 2>&1)
status=$?
ok=1
expect_status $name 1 || ok=0
expect_output $name "Smoke check failed" || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=smoke_checks_a_live_agent_when_given
run "$name" 0123abc STUB_IMAGE_IN_ECR=0 SMOKE_AGENT_ID=agt_missing
ok=1
expect_status $name 1 || ok=0
expect_output $name "widget shell: /widget/a/agt_missing answered 404" || ok=0
[ $ok = 1 ] && echo "ok   $name"

# --- Nothing is touched when the inputs are wrong --------------------------------------------------------------------

for bad in "" latest "has space" "../etc" "$(printf 'a%.0s' $(seq 129))"; do
  name="rejects_the_tag_'${bad:0:20}'"
  run "$name" "$bad" STUB_IMAGE_IN_ECR=0
  ok=1
  expect_status "$name" 2 || ok=0
  [ -z "$calls" ] || { fail "$name" "calls were made: $calls"; ok=0; }
  [ $ok = 1 ] && echo "ok   $name"
done

name=requires_the_state_bucket
run "$name" 0123abc STUB_IMAGE_IN_ECR=0 TF_STATE_BUCKET=
ok=1
expect_status $name 2 || ok=0
expect_output $name "TF_STATE_BUCKET" || ok=0
[ -z "$calls" ] || { fail $name "calls were made"; ok=0; }
[ $ok = 1 ] && echo "ok   $name"

name=requires_the_frontend_builds
run "$name" 0123abc STUB_IMAGE_IN_ECR=0 STUDIO_DIST="$work/nowhere"
ok=1
expect_status $name 2 || ok=0
expect_output $name "pnpm build" || ok=0
[ -z "$calls" ] || { fail $name "calls were made"; ok=0; }
[ $ok = 1 ] && echo "ok   $name"

name=requires_the_demo_pages
run "$name" 0123abc STUB_IMAGE_IN_ECR=0 DEMO_DIST="$work/nowhere"
ok=1
expect_status $name 2 || ok=0
expect_output $name "DEMO_DIST must hold the demo pages" || ok=0
[ -z "$calls" ] || { fail $name "calls were made"; ok=0; }
[ $ok = 1 ] && echo "ok   $name"

exit $((failures > 0))
