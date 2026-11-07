#!/usr/bin/env bash
# shellcheck disable=SC2016,SC2329 # Literal code snippets in single quotes; functions called from traps or loops.
# A dry run of the deploy and destroy workflows' scripts with stubbed cloud CLIs (scripts/deploy/tests/stubs), so
# nothing reaches AWS: terraform, aws and docker only log their arguments. The static upload uses the real
# `pnpm build` output, and the smoke check runs with curl against a local server that serves the real Studio
# index.html, a healthy /api/health and a widget shell with `frame-ancestors *`.
# Usage, from the repository root after `cd frontend && pnpm build`:
#   docs/tickets/09-terraform-deploy/09-06-evidence/dry-run.sh > docs/tickets/09-terraform-deploy/09-06-evidence/dry-run.log
set -uo pipefail
repo=$(pwd)
stubs=$repo/scripts/deploy/tests/stubs
work=$(mktemp -d)
trap 'kill "$site" 2>/dev/null; rm -rf "$work"' EXIT

jq -n --rawfile studio frontend/apps/studio/dist/index.html '{
  "/api/health": {status: 200, headers: {"Content-Type": "application/json"}, body: "{\"status\":\"ok\",\"checks\":{\"database\":\"ok\",\"redis\":\"ok\"}}"},
  "/": {status: 200, headers: {"Content-Type": "text/html"}, body: $studio},
  "/widget/a/smoke-check": {status: 404, headers: {"Content-Type": "text/html; charset=utf-8", "Content-Security-Policy": "frame-ancestors *"}, body: "unavailable"}
}' >"$work/site.json"
python3 -I scripts/deploy/tests/fake_site.py "$work/site.json" >"$work/port" &
site=$!
for _ in $(seq 100); do [ -s "$work/port" ] && break; sleep 0.05; done
url="http://127.0.0.1:$(cat "$work/port")"

jq -n --arg url "$url" '{
  image_tag: "30f00be", cluster_name: "studio-demo-ecs",
  services: {api: "studio-demo-ecs-api", beat: "studio-demo-ecs-beat", worker: "studio-demo-ecs-worker"},
  task_definition_arns: {
    api: "arn:aws:ecs:eu-west-2:123456789012:task-definition/studio-demo-ecs-api:2",
    beat: "arn:aws:ecs:eu-west-2:123456789012:task-definition/studio-demo-ecs-beat:2",
    worker: "arn:aws:ecs:eu-west-2:123456789012:task-definition/studio-demo-ecs-worker:2"},
  migration_task: {task_definition_arn: "arn:aws:ecs:eu-west-2:123456789012:task-definition/studio-demo-ecs-migrate:2",
    container_name: "migrate", subnet_ids: ["subnet-0ccccccccccccccc3", "subnet-0ddddddddddddddd4"], security_group_id: "sg-0migrate000000001"},
  static_bucket_name: "studio-demo-static-123456789012", cloudfront_distribution_id: "E2EXAMPLE0ABCD", cloudfront_url: $url}' >"$work/deploy.json"

run() { # <label> <script> <args...>
  local label=$1
  shift
  : >"$work/calls"
  echo "### $label"
  echo "\$ $*"
  env PATH="$stubs:$PATH" STUB_CALLS="$work/calls" STUB_DEPLOY_JSON="$work/deploy.json" STUB_UPLOADED="$work/uploaded" \
    STUB_IMAGE_IN_ECR="${IN_ECR:-254}" STUB_LOCAL_IMAGES=1 TF_STATE_BUCKET=rag-agent-studio-tfstate-123456789012 AWS_REGION=eu-west-2 \
    SMOKE_ATTEMPTS=1 SMOKE_DELAY_SECONDS=0 "$@" 2>&1
  echo "exit $?"
  echo "--- cloud CLI calls, in order:"
  sed 's/^/    /' "$work/calls"
  echo
}

run "Deploy at a tag that is only built locally (first deploy)" scripts/deploy/deploy.sh 30f00be
echo "--- static bucket contents after the sync:"
(cd "$work/uploaded" && find . -type f | sort | sed 's/^/    /')
echo
IN_ECR=0 run "Redeploy a tag already in ECR" scripts/deploy/deploy.sh 30f00be
run "Destroy with a mistyped confirmation" scripts/deploy/destroy.sh "destroy"
run "Destroy with the typed confirmation" scripts/deploy/destroy.sh "destroy demo"
