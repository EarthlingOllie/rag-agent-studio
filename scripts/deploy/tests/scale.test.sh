#!/usr/bin/env bash
# Tests for scripts/deploy/scale.sh, the scaling demonstration (ticket 22-07). terraform and aws are stubs (tests/stubs)
# that log every call; aws answers each poll from a timeline file, one line per poll:
#   <api running> <api desired> <general running> <general desired> <runs running> <runs desired>
#   <general visible> <general in flight> <runs visible> <runs in flight>      ("-": CloudWatch has no data point)
# The Studio is a local HTTP server (fake_api.py) answering the routes each case gives, so the real curl calls run and
# every request, its session cookie and its body are logged. sleep is stubbed (tests/stubs-clock) except where a case
# needs real time. Nothing calls AWS.
# Usage: scripts/deploy/tests/scale.test.sh
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
scale="$here/../scale.sh"
documents="$here/../../../seed/documents"
work=$(mktemp -d)
pids=()
# shellcheck disable=SC2329 # Called by the EXIT trap.
cleanup() { for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null; done; rm -rf "$work"; }
trap cleanup EXIT
failures=0

fail() { echo "FAIL $1: $2"; failures=$((failures + 1)); }

org=0b6f6d1e-0000-4000-8000-000000000001
seeded=0b6f6d1e-0000-4000-8000-0000000000aa
project=0b6f6d1e-0000-4000-8000-0000000000bb
hr=0b6f6d1e-0000-4000-8000-0000000000c1
faq=0b6f6d1e-0000-4000-8000-0000000000c2
archived=0b6f6d1e-0000-4000-8000-0000000000c3
run1=0b6f6d1e-0000-4000-8000-0000000000d1
run2=0b6f6d1e-0000-4000-8000-0000000000d2
upload=0b6f6d1e-0000-4000-8000-0000000000e1
P=/api/organisations/$org/projects

# What `terraform output -json deploy` prints after a deploy that has the job queues.
deploy_json() {
  jq -n '{
    cluster_name: "studio-demo-ecs",
    services: {api: "studio-demo-ecs-api", "worker-general": "studio-demo-ecs-worker-general",
      "worker-runs": "studio-demo-ecs-worker-runs", beat: "studio-demo-ecs-beat"},
    queue_names: {general: "studio-demo-queue-general", runs: "studio-demo-queue-runs"},
    cloudfront_url: "https://d111111abcdef8.cloudfront.net"
  }'
}

# The seeded demo's Studio: the Owner signs in, the throwaway Project is created, archived and deleted, uploads are
# accepted, the seeded Project's HR helper takes Runs (one at a time) and the Product FAQ has no Evaluation Set.
# Each argument is a jq expression that changes the routes.
studio() {
  jq -n --arg P "$P" --arg org "$org" --arg seeded "$seeded" --arg project "$project" --arg hr "$hr" --arg faq "$faq" \
    --arg archived "$archived" --arg run1 "$run1" --arg run2 "$run2" --arg upload "$upload" '
    def ok($status; $body): {status: $status, body: $body};
    def run($id): ok(202; {id: $id, status: "queued"});
    def busy: ok(409; {detail: "The Agent already has a Run in progress.", conflict: {kind: "run", run_id: $run1}});
    {
      "POST /api/auth/sign-in": {status: 200, headers: {"Set-Cookie": "studio_session=s3cr3t; Path=/; HttpOnly"},
        body: {member: {id: "m1"}, active_organisation_id: $org,
               organisations: [{id: $org, name: "Northwind Traders", role: "owner", mfa_required: false}]}},
      ("POST " + $P): ok(201; {id: $project, name: "Scaling demonstration"}),
      ("GET " + $P): ok(200; [
        {id: $seeded, name: "Northwind Handbook", archived_at: null, deleting: false},
        {id: $project, name: "Scaling demonstration", archived_at: null, deleting: false},
        {id: "old", name: "Old", archived_at: "2026-10-01T00:00:00Z", deleting: false}]),
      ("GET " + $P + "/" + $seeded + "/agents"): ok(200; [
        {id: $hr, name: "HR helper", archived_at: null}, {id: $faq, name: "Product FAQ", archived_at: null},
        {id: $archived, name: "Retired", archived_at: "2026-10-01T00:00:00Z"}]),
      ("POST " + $P + "/" + $seeded + "/agents/" + $hr + "/evaluation/runs"): [run($run1), busy, run($run2), busy],
      ("POST " + $P + "/" + $seeded + "/agents/" + $faq + "/evaluation/runs"):
        ok(409; {detail: "The Evaluation Set is empty.", conflict: null}),
      ("POST " + $P + "/" + $seeded + "/agents/" + $hr + "/evaluation/runs/" + $run1 + "/cancel"): ok(409; {detail: "The Run has already finished."}),
      ("POST " + $P + "/" + $seeded + "/agents/" + $hr + "/evaluation/runs/" + $run2 + "/cancel"): ok(200; {id: $run2, status: "cancelled"}),
      ("POST " + $P + "/" + $project + "/uploads"):
        ok(201; {upload_id: $upload, url: "{base}/presigned/upload", content_type: "text/markdown", expires_at: "2026-11-26T12:00:00Z", method: "PUT"}),
      "PUT /presigned/upload": {status: 200, body: ""},
      ("POST " + $P + "/" + $project + "/documents"): ok(201; {id: "d", status: "queued"}),
      ("POST " + $P + "/" + $project + "/archive"): ok(200; {id: $project, archived_at: "2026-11-26T12:00:00Z"}),
      ("DELETE " + $P + "/" + $project): {status: 202, body: ""}
    }' | jq "${@:-.}"
}

# A timeline that scales every service out and back in.
SCALES_OUT_AND_IN='1 1 1 1 0 0 0 0 0 0
1 2 1 3 0 1 14 2 1 0
2 3 3 3 1 1 8 6 0 1
3 3 3 3 1 1 0 4 0 0
2 1 2 1 0 0 0 0 - -
1 1 1 1 0 0 0 0 0 0'

url=""
# serve <case dir> <routes json>: starts a fake Studio for the case and sets $url to it.
serve() {
  local routes="$1/routes.json" port=""
  printf '%s' "$2" >"$routes"
  python3 -I "$here/fake_api.py" "$routes" >"$routes.port" 2>/dev/null &
  pids+=("$!")
  for _ in $(seq 100); do
    port=$(cat "$routes.port")
    [ -n "$port" ] && break
    sleep 0.05
  done
  url="http://127.0.0.1:$port"
}

# run <case> <routes json> <timeline> [scale.sh options...] [-- VAR=value...]: runs scale.sh against a fresh fake Studio,
# with the stubs and quick defaults (1-second load, 1-second polls); sets $status, $out, $calls (aws and terraform) and
# $requests (the Studio's log).
run() {
  local name=$1 routes=$2 timeline=$3 args=() vars=()
  shift 3
  while [ $# -gt 0 ] && [ "$1" != -- ]; do args+=("$1"); shift; done
  [ "${1:-}" = -- ] && { shift; vars=("$@"); }
  dir="$work/$name"
  mkdir -p "$dir"
  : >"$dir/calls"
  printf '%s\n' "$timeline" >"$dir/timeline"
  [ -f "$dir/deploy.json" ] || deploy_json >"$dir/deploy.json"
  serve "$dir" "$routes"
  out=$(env PATH="$here/stubs:$here/stubs-clock:$PATH" STUB_CALLS="$dir/calls" STUB_DEPLOY_JSON="$dir/deploy.json" \
    STUB_TIMELINE="$dir/timeline" TF_STATE_BUCKET=rag-agent-studio-tfstate-123456789012 AWS_REGION=eu-west-2 \
    DEPLOY_ROOT=/repo/infra/envs/demo OWNER_EMAIL=owner@northwind.example OWNER_PASSWORD='north"wind owner' \
    "${vars[@]}" "$scale" --api-seconds 1 --api-workers 2 --poll-seconds 1 "${args[@]}" "$url" 2>&1)
  status=$?
  calls=$(cat "$dir/calls")
  requests=$(cat "$dir/routes.json.log" 2>/dev/null)
}

expect_status() { if [ "$status" != "$2" ]; then fail "$1" "exit $status, expected $2. Output: $out"; return 1; fi; }
expect_output() { if ! grep -qF -- "$2" <<<"$out"; then fail "$1" "expected '$2' in: $out"; return 1; fi; }
no_output() { if grep -qF -- "$2" <<<"$out"; then fail "$1" "unexpected '$2' in: $out"; return 1; fi; }
expect_request() { if ! grep -qF -- "$2" <<<"$requests"; then fail "$1" "expected the request '$2' in: $requests"; return 1; fi; }
no_request() { if grep -qF -- "$2" <<<"$requests"; then fail "$1" "unexpected request '$2' in: $requests"; return 1; fi; }
count() { grep -cF -- "$2" <<<"$1"; }
# deleted <case>: the throwaway Project was archived, then deleted with its name typed as the confirmation.
deleted() {
  local archive delete
  archive=$(grep -nF "POST $P/$project/archive " <<<"$requests" | cut -d: -f1)
  delete=$(grep -nF "DELETE $P/$project cookie=studio_session=s3cr3t body={\"confirm_name\":\"Scaling demonstration " <<<"$requests" | cut -d: -f1)
  if [ -z "$archive" ] || [ -z "$delete" ] || [ "$archive" -gt "$delete" ]; then
    fail "$1" "the Project was not archived and then deleted: $requests"; return 1
  fi
  expect_output "$1" "Deleted the Project 'Scaling demonstration "
}

# --- The happy path -------------------------------------------------------------------------------------------------

name=puts_work_on_the_demo_and_prints_a_timeline_until_every_service_is_back_at_its_minimum
run "$name" "$(studio)" "$SCALES_OUT_AND_IN"
ok=1
expect_status $name 0 || ok=0
# The deployed environment comes from the deploy output; nothing is applied.
[ "$(grep -c '^terraform' <<<"$calls")" = 2 ] || { fail $name "terraform calls: $calls"; ok=0; }
grep -qxF 'terraform -chdir=/repo/infra/envs/demo output -json deploy' <<<"$calls" || { fail $name "no deploy output read"; ok=0; }
# AWS is only read: the scalable targets' minimums, the services' task counts and the queues' depth.
if grep '^aws' <<<"$calls" | grep -vqE '^aws (ecs describe-services|cloudwatch get-metric-data|application-autoscaling describe-scalable-targets) '; then
  fail $name "an AWS call that is not a read: $calls"; ok=0
fi
grep -qxF 'aws application-autoscaling describe-scalable-targets --service-namespace ecs --resource-ids service/studio-demo-ecs/studio-demo-ecs-api service/studio-demo-ecs/studio-demo-ecs-worker-general service/studio-demo-ecs/studio-demo-ecs-worker-runs --query ScalableTargets[].[ResourceId,MinCapacity] --output text' <<<"$calls" ||
  { fail $name "minimums not read from the scalable targets: $calls"; ok=0; }
grep -qxF 'aws ecs describe-services --cluster studio-demo-ecs --services studio-demo-ecs-api studio-demo-ecs-worker-general studio-demo-ecs-worker-runs --query services[].[serviceName,runningCount,desiredCount] --output text' <<<"$calls" ||
  { fail $name "task counts not read from ECS: $calls"; ok=0; }
metrics=$(grep '^aws cloudwatch get-metric-data' <<<"$calls" | head -n 1)
for q in '"Id":"general_visible"' '"Id":"general_in_flight"' '"Id":"runs_visible"' '"Id":"runs_in_flight"' \
  '"QueueName","Value":"studio-demo-queue-general"' '"QueueName","Value":"studio-demo-queue-runs"' \
  '"MetricName":"ApproximateNumberOfMessagesVisible"' '"MetricName":"ApproximateNumberOfMessagesNotVisible"'; do
  grep -qF -- "$q" <<<"$metrics" || { fail $name "queue depth query lacks $q: $metrics"; ok=0; }
done
# One poll per timeline line: it stops as soon as the load is over and every service is back at its minimum.
[ "$(count "$calls" 'aws ecs describe-services')" = 6 ] || { fail $name "polls: $(count "$calls" 'aws ecs describe-services')"; ok=0; }
[ "$(count "$calls" 'sleep 1')" = 5 ] || { fail $name "waits between polls: $calls"; ok=0; }
# The timeline: queue depth (visible+in flight) and running/desired tasks per service.
expect_output $name "general queue" || ok=0
expect_output $name "worker-general" || ok=0
grep -qE '^[0-9:]{8} +00:00 +0\+0 +0\+0 +1/1 +1/1 +0/0 *$' <<<"$out" || { fail $name "no first row: $out"; ok=0; }
grep -qE '^[0-9:]{8} +00:01 +14\+2 +1\+0 +1/2 +1/3 +0/1 *$' <<<"$out" || { fail $name "no scale-out row: $out"; ok=0; }
grep -qE '^[0-9:]{8} +00:04 +0\+0 +-\+- +2/1 +2/1 +0/0 *$' <<<"$out" || { fail $name "no row without data: $out"; ok=0; }
expect_output $name "api 1 -> 3 -> 1, worker-general 1 -> 3 -> 1, worker-runs 0 -> 1 -> 0" || ok=0
# The work: the Owner signs in, then every request carries the session.
expect_request $name 'POST /api/auth/sign-in cookie= body={"email":"owner@northwind.example","password":"north\"wind owner"}' || ok=0
if grep -v '^POST /api/auth/sign-in\|^PUT /presigned' <<<"$requests" | grep -qv 'cookie=studio_session=s3cr3t'; then
  fail $name "a request without the session: $requests"; ok=0
fi
expect_request $name "POST $P cookie=studio_session=s3cr3t body={\"name\":\"Scaling demonstration " || ok=0
# Each seed Document five times (the default), under different names and with different content.
[ "$(count "$requests" "POST $P/$project/uploads ")" = 20 ] || { fail $name "uploads started: $requests"; ok=0; }
[ "$(count "$requests" "POST $P/$project/documents cookie=studio_session=s3cr3t body={\"upload_id\":\"$upload\"}")" = 20 ] || { fail $name "uploads confirmed: $requests"; ok=0; }
[ "$(grep '^PUT /presigned/upload' <<<"$requests" | sort -u | wc -l | tr -d ' ')" = 20 ] || { fail $name "uploaded files are not all different: $requests"; ok=0; }
for f in "$documents"/*; do
  for c in 1 5; do
    size=$(wc -c <"$f" | tr -d ' ')
    grep -qE "^POST $P/$project/uploads .*body=\\{\"filename\":\"scale-$c-$(basename "$f")\",\"size_bytes\":[0-9]+\\}" <<<"$requests" || { fail $name "no upload of copy $c of $(basename "$f"): $requests"; ok=0; }
    grep -qF "\"filename\":\"scale-$c-$(basename "$f")\",\"size_bytes\":$size}" <<<"$requests" && { fail $name "copy $c of $(basename "$f") is the seed file unchanged"; ok=0; }
  done
done
expect_output $name "Uploaded 20 Documents" || ok=0
# Runs on the seeded Agents: one at a time on the HR helper, none on an Agent without an Evaluation Set or archived.
[ "$(count "$requests" "POST $P/$seeded/agents/$hr/evaluation/runs ")" -ge 1 ] || { fail $name "no Run started: $requests"; ok=0; }
no_request $name "/agents/$archived/" || ok=0
[ "$(count "$requests" "POST $P/$seeded/agents/$faq/evaluation/runs ")" = 1 ] || { fail $name "the Agent without an Evaluation Set was asked again: $requests"; ok=0; }
expect_output $name "Started an Evaluation Run on HR helper" || ok=0
expect_output $name "No Evaluation Run on Product FAQ: The Evaluation Set is empty." || ok=0
# API traffic for the load's length.
[ "$(count "$requests" "GET $P cookie=studio_session=s3cr3t")" -ge 3 ] || { fail $name "no API traffic: $requests"; ok=0; }
expect_output $name "API requests sent" || ok=0
# A finished demonstration cancels nothing and deletes its Project.
no_request $name "/cancel" || ok=0
deleted $name || ok=0
[ $ok = 1 ] && echo "ok   $name"

# --- Load sizes are arguments ---------------------------------------------------------------------------------------

name=takes_the_copies_and_runs_as_arguments
run "$name" "$(studio)" "$SCALES_OUT_AND_IN" --copies 2 --runs 2 --api-seconds 3
ok=1
expect_status $name 0 || ok=0
[ "$(count "$requests" "POST $P/$project/uploads ")" = 8 ] || { fail $name "uploads: $(count "$requests" "POST $P/$project/uploads ")"; ok=0; }
expect_output $name "Uploaded 8 Documents" || ok=0
# Runs are asked for at each poll of the load (three here). The HR helper answers 202, 409 (busy), 202: two Runs,
# then no more are asked for.
[ "$(count "$requests" "POST $P/$seeded/agents/$hr/evaluation/runs ")" = 3 ] || { fail $name "Run requests: $requests"; ok=0; }
[ "$(count "$out" "Started an Evaluation Run on HR helper")" = 2 ] || { fail $name "Runs started: $out"; ok=0; }
[ $ok = 1 ] && echo "ok   $name"

name=a_longer_load_keeps_polling_while_it_lasts
run "$name" "$(studio)" '0 0 0 0 0 0 0 0 0 0' --api-seconds 2 --poll-seconds 1 -- STUB_MINIMUMS='0 0 0'
# Everything is at its minimum from the start, but nothing is judged before the load is over (the third poll).
ok=1
[ "$(count "$calls" 'aws ecs describe-services')" = 3 ] || { fail $name "polls: $calls"; ok=0; }
[ $ok = 1 ] && echo "ok   $name"

name=shows_its_defaults_in_the_usage
out=$("$scale" --help 2>&1); status=$?
ok=1
expect_status $name 2 || ok=0
for d in "--copies N        each seed Document is uploaded N times (default 5)" "--runs N" "(default 3)" "--api-seconds N" "(default 300)" \
  "--api-workers N" "(default 8)" "--poll-seconds N" "(default 30)" "--timeout-minutes N" "(default 25)"; do
  expect_output $name "$d" || ok=0
done
[ $ok = 1 ] && echo "ok   $name"

# --- A service that never scales out --------------------------------------------------------------------------------

name=fails_naming_the_runs_pool_when_it_never_scaled_out
run "$name" "$(studio)" '1 1 1 1 0 0 0 0 0 0
3 3 3 3 0 0 9 2 0 0
1 1 1 1 0 0 0 0 0 0' --api-seconds 3
ok=1
expect_status $name 1 || ok=0
expect_output $name "::error title=Did not scale out::worker-runs never scaled out: it stayed at 0 tasks" || ok=0
no_output $name "api never scaled out" || ok=0
no_output $name "worker-general never scaled out" || ok=0
deleted $name || ok=0
# After a failure the Runs it started are cancelled: the first had already finished (409), the second is cancelled.
expect_request $name "POST $P/$seeded/agents/$hr/evaluation/runs/$run1/cancel " || ok=0
expect_request $name "POST $P/$seeded/agents/$hr/evaluation/runs/$run2/cancel " || ok=0
[ "$(count "$out" "Cancelled the Evaluation Run on HR helper.")" = 1 ] || { fail $name "cancellations: $out"; ok=0; }
[ $ok = 1 ] && echo "ok   $name"

name=fails_naming_the_api_when_it_never_scaled_out
run "$name" "$(studio)" '1 1 1 1 0 0 0 0 0 0
1 1 3 3 1 1 9 2 1 0
1 1 1 1 0 0 0 0 0 0'
ok=1
expect_status $name 1 || ok=0
expect_output $name "::error title=Did not scale out::api never scaled out: it stayed at 1 task" || ok=0
no_output $name "worker-runs never scaled out" || ok=0
deleted $name || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=a_desired_count_alone_is_not_a_scale_out
run "$name" "$(studio)" '1 1 1 1 0 0 0 0 0 0
2 2 3 3 0 2 9 2 1 0
1 1 1 1 0 0 0 0 0 0'
ok=1
expect_status $name 1 || ok=0
expect_output $name "worker-runs never scaled out" || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=fails_naming_the_service_that_never_came_back_to_its_minimum
run "$name" "$(studio)" '1 1 1 1 0 0 0 0 0 0
3 3 3 3 1 1 9 2 1 0
1 1 2 2 0 0 0 0 0 0' --poll-seconds 10 --timeout-minutes 1
ok=1
expect_status $name 1 || ok=0
expect_output $name "::error title=Did not scale in::worker-general is not back at its minimum of 1 task after 1 minutes (2 running, 2 desired)" || ok=0
no_output $name "api is not back" || ok=0
[ "$(count "$calls" 'aws ecs describe-services')" = 6 ] || { fail $name "polls: $(count "$calls" 'aws ecs describe-services')"; ok=0; }
expect_request $name "/evaluation/runs/$run1/cancel" || ok=0
deleted $name || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=a_queue_still_holding_jobs_keeps_it_polling
run "$name" "$(studio)" '1 1 1 1 0 0 0 0 0 0
3 3 3 3 1 1 9 2 1 0
1 1 1 1 0 0 0 0 0 0
1 1 1 1 0 0 0 0 0 1
1 1 1 1 0 0 0 0 0 0'
ok=1
expect_status $name 0 || ok=0
# The third line is at every minimum with empty queues; the fourth has a job in flight; the fifth ends it.
[ "$(count "$calls" 'aws ecs describe-services')" = 3 ] || { fail $name "polls: $(count "$calls" 'aws ecs describe-services')"; ok=0; }
[ $ok = 1 ] && echo "ok   $name"

# --- Clean-up when interrupted --------------------------------------------------------------------------------------

name=deletes_its_project_and_cancels_its_runs_when_interrupted
dir="$work/$name"; mkdir -p "$dir"; : >"$dir/calls"
printf '%s\n' '1 2 1 3 0 1 14 2 1 0' >"$dir/timeline"
deploy_json >"$dir/deploy.json"
serve "$dir" "$(studio)"
# Real sleep here: the demonstration is still polling when it is stopped.
env PATH="$here/stubs:$PATH" STUB_CALLS="$dir/calls" STUB_DEPLOY_JSON="$dir/deploy.json" STUB_TIMELINE="$dir/timeline" \
  TF_STATE_BUCKET=b AWS_REGION=eu-west-2 DEPLOY_ROOT=/repo/infra/envs/demo OWNER_EMAIL=o@e OWNER_PASSWORD=p \
  "$scale" --api-seconds 30 --api-workers 2 --poll-seconds 1 --copies 1 "$url" >"$dir/out" 2>&1 &
demo=$!
for _ in $(seq 200); do grep -q '^[0-9:]\{8\} ' "$dir/out" && break; sleep 0.1; done
kill -TERM "$demo"
wait "$demo"; status=$?
out=$(cat "$dir/out"); requests=$(cat "$dir/routes.json.log")
ok=1
[ "$status" != 0 ] || { fail $name "exit 0 after being stopped"; ok=0; }
grep -q '^[0-9:]\{8\} ' <<<"$out" || { fail $name "it never reached the timeline: $out"; ok=0; }
expect_request $name "/evaluation/runs/$run1/cancel" || ok=0
deleted $name || ok=0
# The API traffic stops with it.
sleep 1
before=$(count "$(cat "$dir/routes.json.log")" "GET $P "); sleep 1; after=$(count "$(cat "$dir/routes.json.log")" "GET $P ")
[ "$before" = "$after" ] || { fail $name "API traffic goes on after it stopped ($before, then $after)"; ok=0; }
[ $ok = 1 ] && echo "ok   $name"

# --- Refusals before any work -----------------------------------------------------------------------------------------

name=fails_when_the_owner_cannot_sign_in
run "$name" "$(studio '."POST /api/auth/sign-in" = {status: 401, body: {detail: "Wrong email or password."}}')" "$SCALES_OUT_AND_IN"
ok=1
expect_status $name 1 || ok=0
expect_output $name "sign-in answered 401: Wrong email or password." || ok=0
no_request $name "POST $P " || ok=0
no_output $name "Deleted" || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=fails_when_the_owner_uses_mfa
run "$name" "$(studio '."POST /api/auth/sign-in" = {status: 202, body: {mfa_required: true}}')" "$SCALES_OUT_AND_IN"
ok=1
expect_status $name 1 || ok=0
expect_output $name "uses MFA" || ok=0
no_request $name "POST $P " || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=fails_when_the_member_is_not_an_owner
run "$name" "$(studio '."POST /api/auth/sign-in".body.organisations[0].role = "editor"')" "$SCALES_OUT_AND_IN"
ok=1
expect_status $name 1 || ok=0
expect_output $name "is not an Owner" || ok=0
no_request $name "POST $P " || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=fails_when_the_demo_is_not_seeded
run "$name" "$(studio --arg s "GET $P/$seeded/agents" '.[$s].body = []')" "$SCALES_OUT_AND_IN"
ok=1
expect_status $name 1 || ok=0
expect_output $name "no seeded Agents: seed the demo first (scripts/deploy/seed.sh)" || ok=0
deleted $name || ok=0
no_output $name "general queue" || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=fails_and_cleans_up_when_an_upload_is_refused
run "$name" "$(studio --arg s "POST $P/$project/documents" '.[$s] = {status: 409, body: {detail: "That file is already in the Project."}}')" "$SCALES_OUT_AND_IN"
ok=1
expect_status $name 1 || ok=0
expect_output $name "confirming the upload of scale-1-" || ok=0
expect_output $name "answered 409: That file is already in the Project." || ok=0
deleted $name || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=fails_and_cleans_up_when_the_presigned_upload_fails
run "$name" "$(studio '."PUT /presigned/upload" = {status: 403, body: "<Error>SignatureDoesNotMatch</Error>"}')" "$SCALES_OUT_AND_IN"
ok=1
expect_status $name 1 || ok=0
expect_output $name "the presigned upload of scale-1-" || ok=0
deleted $name || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=says_so_when_its_project_could_not_be_deleted
run "$name" "$(studio --arg s "DELETE $P/$project" '.[$s] = {status: 500, body: {detail: "Internal Server Error"}}')" "$SCALES_OUT_AND_IN"
ok=1
expect_status $name 1 || ok=0
expect_output $name "::error title=Project not deleted::" || ok=0
expect_output $name "delete it in the Studio" || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=fails_when_the_project_cannot_be_created
run "$name" "$(studio --arg s "POST $P" '.[$s] = {status: 404, body: {detail: "Not Found"}}')" "$SCALES_OUT_AND_IN"
ok=1
expect_status $name 1 || ok=0
expect_output $name "creating the Project answered 404" || ok=0
no_output $name "Deleted" || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=fails_when_the_environment_is_not_deployed
run "$name" "$(studio)" "$SCALES_OUT_AND_IN" -- STUB_TF_OUTPUT_EXIT=1
ok=1
expect_status $name 1 || ok=0
expect_output $name "The demo environment is not deployed" || ok=0
[ -z "$requests" ] || { fail $name "the Studio was called: $requests"; ok=0; }
[ $ok = 1 ] && echo "ok   $name"

name=fails_when_the_deploy_output_has_no_job_queues
mkdir -p "$work/$name"; deploy_json | jq 'del(.queue_names)' >"$work/$name/deploy.json"
run "$name" "$(studio)" "$SCALES_OUT_AND_IN"
ok=1
expect_status $name 1 || ok=0
expect_output $name "no job queues" || ok=0
[ -z "$requests" ] || { fail $name "the Studio was called: $requests"; ok=0; }
[ $ok = 1 ] && echo "ok   $name"

name=fails_when_the_studio_is_unreachable
dir="$work/$name"; mkdir -p "$dir"; : >"$dir/calls"; deploy_json >"$dir/deploy.json"; printf '1 1 1 1 0 0 0 0 0 0\n' >"$dir/timeline"
out=$(env PATH="$here/stubs:$here/stubs-clock:$PATH" STUB_CALLS="$dir/calls" STUB_DEPLOY_JSON="$dir/deploy.json" STUB_TIMELINE="$dir/timeline" \
  TF_STATE_BUCKET=b AWS_REGION=eu-west-2 DEPLOY_ROOT=/r OWNER_EMAIL=o@e OWNER_PASSWORD=p "$scale" http://127.0.0.1:9 2>&1); status=$?
ok=1
expect_status $name 1 || ok=0
expect_output $name "sign-in answered 000" || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=copies_pdf_and_text_documents_too
mkdir -p "$work/docs"; printf '%%PDF-1.4\n%%%%EOF\n' >"$work/docs/notes.pdf"; printf 'plain\n' >"$work/docs/notes.txt"
run "$name" "$(studio)" "$SCALES_OUT_AND_IN" --copies 2 -- SCALE_DOCUMENTS_DIR="$work/docs"
ok=1
expect_status $name 0 || ok=0
expect_output $name "Uploaded 4 Documents" || ok=0
[ "$(grep '^PUT /presigned/upload' <<<"$requests" | sort -u | wc -l | tr -d ' ')" = 4 ] || { fail $name "uploaded files are not all different: $requests"; ok=0; }
grep -qF '"filename":"scale-2-notes.pdf","size_bytes":47}' <<<"$requests" || { fail $name "the PDF copy: $requests"; ok=0; }
grep -qF '"filename":"scale-1-notes.txt","size_bytes":46}' <<<"$requests" || { fail $name "the text copy: $requests"; ok=0; }
[ $ok = 1 ] && echo "ok   $name"

name=refuses_a_document_it_cannot_copy
mkdir -p "$work/images"; printf 'png' >"$work/images/logo.png"
run "$name" "$(studio)" "$SCALES_OUT_AND_IN" -- SCALE_DOCUMENTS_DIR="$work/images"
ok=1
expect_status $name 1 || ok=0
expect_output $name "logo.png is not a type this script can copy" || ok=0
deleted $name || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=fails_when_a_service_has_no_scalable_target
run "$name" "$(studio)" "$SCALES_OUT_AND_IN" -- STUB_MINIMUMS='1 1 none'
ok=1
expect_status $name 1 || ok=0
expect_output $name "worker-runs has no scalable target" || ok=0
[ -z "$requests" ] || { fail $name "the Studio was called: $requests"; ok=0; }
[ $ok = 1 ] && echo "ok   $name"

# --- Arguments and settings ---------------------------------------------------------------------------------------------

for args in "" "ftp://example.com" "https://d111111abcdef8.cloudfront.net/studio" "--copies" "--copies 0 https://x.example" \
  "--runs two https://x.example" "--bogus https://x.example" "https://a.example https://b.example"; do
  # shellcheck disable=SC2086 # Each case is several words.
  if out=$(OWNER_EMAIL=o@e OWNER_PASSWORD=p TF_STATE_BUCKET=b AWS_REGION=r "$scale" $args 2>&1); then
    fail "rejects_bad_arguments '$args'" "exit 0"
  elif grep -qF "usage:" <<<"$out"; then echo "ok   rejects_bad_arguments '$args'"
  else fail "rejects_bad_arguments '$args'" "$out"; fi
done

for missing in OWNER_EMAIL OWNER_PASSWORD TF_STATE_BUCKET AWS_REGION; do
  name="needs_$missing"
  out=$(env OWNER_EMAIL=o@e OWNER_PASSWORD=p TF_STATE_BUCKET=b AWS_REGION=r "$missing=" "$scale" https://x.example 2>&1); status=$?
  ok=1
  expect_status "$name" 2 || ok=0
  expect_output "$name" "$missing must" || ok=0
  [ $ok = 1 ] && echo "ok   $name"
done

exit $((failures > 0))
