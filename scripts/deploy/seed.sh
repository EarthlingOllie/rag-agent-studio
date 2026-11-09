#!/usr/bin/env bash
# Seeds the deployed demo environment with the demo data (ticket 10-05; spec 10 story 4), as `make seed` does locally.
# The seed workflow runs it; it also runs by hand with AWS credentials for the account. In order:
#   1. terraform init against the bootstrap's state bucket and read the deploy output (nothing is applied)
#   2. run the seed task (`python -m app.seed`, or `--reset` with --reset) once on Fargate, in the private subnets
#   3. wait for it to stop, in rounds of the ECS waiter's ten minutes, and fail on anything but exit 0
#   4. print the task's log, which holds the demo sign-in details, and add it to the job summary
# The seed is idempotent: it finds the demo Organisation by its Owner and completes what is missing, so running this
# again duplicates nothing. --reset erases the demo Organisation (only that one) and seeds it again.
# The seed task runs the image the last deploy applied, so deploy first (scripts/deploy/deploy.sh): it runs the
# migrations and starts the worker that ingests the demo Documents.
# Usage: TF_STATE_BUCKET=... AWS_REGION=... scripts/deploy/seed.sh [--reset]
# Optional: DEPLOY_ROOT (default infra/envs/demo), SEED_WAIT_ROUNDS (default 6 waits of up to ten minutes each).
set -euo pipefail

usage() { echo "usage: $0 [--reset]" >&2; exit 2; }
reset=false
case "$#:${1:-}" in
  0:) ;;
  1:--reset) reset=true ;;
  *) usage ;;
esac
[ -n "${TF_STATE_BUCKET:-}" ] || { echo "TF_STATE_BUCKET must name the bootstrap's state bucket (its state_bucket_name output)." >&2; exit 2; }
[ -n "${AWS_REGION:-}" ] || { echo "AWS_REGION must be set." >&2; exit 2; }
rounds=${SEED_WAIT_ROUNDS:-6}
[[ "$rounds" =~ ^[1-9][0-9]*$ ]] || { echo "SEED_WAIT_ROUNDS must be a positive whole number of waits." >&2; exit 2; }
root=${DEPLOY_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)/infra/envs/demo}

step() { echo "==> $*"; }
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# --- 1. The deployed environment ------------------------------------------------------------------------------------
step "terraform init (state bucket $TF_STATE_BUCKET)"
terraform -chdir="$root" init -input=false -backend-config="bucket=$TF_STATE_BUCKET" -backend-config="region=$AWS_REGION"
if ! terraform -chdir="$root" output -json deploy >"$work/deploy.json"; then
  echo "::error title=Not seeded::The demo environment is not deployed. Run the deploy workflow first." >&2
  exit 1
fi
out() { jq -r "$1" "$work/deploy.json"; }
if [ "$(out '.seed_task // empty | .task_definition_arn // empty')" = "" ]; then
  echo "::error title=Not seeded::The deployed environment has no seed task: run the deploy workflow first, at a commit that has it." >&2
  exit 1
fi
cluster=$(out .cluster_name)
container=$(out .seed_task.container_name)

# --- 2. Run the seed task -------------------------------------------------------------------------------------------
network="awsvpcConfiguration={subnets=[$(out '.seed_task.subnet_ids | join(",")')],securityGroups=[$(out .seed_task.security_group_id)],assignPublicIp=DISABLED}"
args=(--cluster "$cluster" --task-definition "$(out .seed_task.task_definition_arn)" --launch-type FARGATE)
if [ "$reset" = true ]; then
  step "Running the seed task with --reset: the demo Organisation is erased and seeded again"
  args+=(--started-by seed-demo-reset --network-configuration "$network"
    --overrides "{\"containerOverrides\":[{\"name\":\"$container\",\"command\":[\"python\",\"-m\",\"app.seed\",\"--reset\"]}]}")
else
  step "Running the seed task"
  args+=(--started-by seed-demo --network-configuration "$network")
fi
task=$(aws ecs run-task "${args[@]}" --query 'tasks[0].taskArn' --output text)
if [[ "$task" != arn:* ]]; then
  echo "::error title=Seed failed::The seed task did not start ($task)." >&2
  exit 1
fi

# --- 3. Wait for it -------------------------------------------------------------------------------------------------
step "Waiting for $task"
stopped=false
for _ in $(seq "$rounds"); do
  if aws ecs wait tasks-stopped --cluster "$cluster" --tasks "$task"; then stopped=true; break; fi
done
if [ "$stopped" != true ]; then
  echo "::error title=Seed failed::The seed task is still running after $rounds waits ($task); see its log group." >&2
  exit 1
fi
exit_code=$(aws ecs describe-tasks --cluster "$cluster" --tasks "$task" \
  --query "tasks[0].containers[?name==\`$container\`].exitCode | [0]" --output text)

# --- 4. Its output --------------------------------------------------------------------------------------------------
# awslogs names each stream <prefix>/<container>/<task ID>; text output puts the messages on one line, tab-separated.
stream="$(out .seed_task.log_stream_prefix)/$container/${task##*/}"
if aws logs get-log-events --log-group-name "$(out .seed_task.log_group_name)" --log-stream-name "$stream" \
  --start-from-head --query 'events[].message' --output text >"$work/log.txt"; then
  tr '\t' '\n' <"$work/log.txt" | tee "$work/seed.log"
else
  echo "Could not read the seed task's log ($stream); see its log group."
  : >"$work/seed.log"
fi

if [ "$exit_code" != 0 ]; then
  echo "::error title=Seed failed::Seed task exited $exit_code ($task); see its output above." >&2
  exit 1
fi
url=$(out .cloudfront_url)
echo "The demo environment is seeded: $url"
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  # shellcheck disable=SC2016 # The backticks are Markdown.
  { printf '### Demo seeded\n\n- URL: %s\n\n```\n' "$url"; cat "$work/seed.log"; printf '```\n'; } >>"$GITHUB_STEP_SUMMARY"
fi
