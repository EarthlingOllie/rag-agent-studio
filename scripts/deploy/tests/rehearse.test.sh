#!/usr/bin/env bash
# Tests for scripts/deploy/rehearse.sh, the wrapper behind `make rehearse` and `make rehearse-down` (ticket 23-03), and
# for scripts/deploy/rehearsal/run-tool.sh, which runs terraform and the AWS CLI on the rehearsal's tools network.
# The wrapper runs in a copy of the repository's layout whose deploy.sh, destroy.sh and tool shims are stubs that log
# their arguments and the settings they were given; docker, make, pnpm and uname are stubs too (tests/stubs-rehearsal).
# Nothing starts a container or calls the emulator.
# Usage: scripts/deploy/tests/rehearse.test.sh
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
failures=0

fail() { echo "FAIL $1: $2"; failures=$((failures + 1)); }

# The repository's layout, with the real wrapper and stub scripts.
repo=$work/repo
mkdir -p "$repo/scripts/deploy/rehearsal" "$repo/infra/rehearsal" "$repo/infra/envs/local" "$repo/frontend"
cp "$here/../rehearse.sh" "$repo/scripts/deploy/"
touch "$repo/infra/rehearsal/compose.yml" "$repo/infra/rehearsal/ca.Dockerfile"
for script in deploy.sh destroy.sh seed.sh scale.sh rehearsal/terraform rehearsal/aws rehearsal/drive-scaling.sh; do
  cat >"$repo/scripts/deploy/$script" <<'EOF'
#!/usr/bin/env bash
# Logs the call, with the settings the rehearsal must give it, and which terraform the PATH finds.
echo "$(basename "$0") $* | DEPLOY_ROOT=${DEPLOY_ROOT:-} TF_STATE_BUCKET=${TF_STATE_BUCKET:-} AWS_ENDPOINT_URL=${AWS_ENDPOINT_URL:-} AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-} AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-} AWS_REGION=${AWS_REGION:-} AWS_SESSION_TOKEN=${AWS_SESSION_TOKEN:-} TF_VAR_cpu_architecture=${TF_VAR_cpu_architecture:-} REHEARSAL_TOOLS_NETWORK=${REHEARSAL_TOOLS_NETWORK:-} TF_DATA_DIR=${TF_DATA_DIR:-} terraform=$(command -v terraform)" >>"$STUB_CALLS"
case "$(basename "$0") $*" in
  "aws s3api head-bucket"*) exit "${STUB_BUCKET_EXISTS_EXIT:-254}" ;;
  deploy.sh*) exit "${STUB_DEPLOY_EXIT:-0}" ;;
  "terraform "*" plan "*) echo "  # module.cdn.aws_cloudfront_function.spa_fallback will be updated in-place"; exit "${STUB_PLAN_EXIT:-0}" ;;
  seed.sh*) exit "${STUB_SEED_EXIT:-0}" ;;
  destroy.sh*) exit "${STUB_DESTROY_EXIT:-0}" ;;
  "terraform "*" output -json deploy") echo '{"cluster_name":"studio-local-ecs","services":{"api":"studio-local-ecs-api"},"queue_names":{"general":"studio-local-queue-general","runs":"studio-local-queue-runs"},"cloudfront_url":"http://e1.cloudfront.localhost:4566"}' ;;
  "terraform "*" output -raw jobs_metric_namespace") printf Rehearsal/SQS ;;
  scale.sh*) echo "scale.sh OWNER_EMAIL=${OWNER_EMAIL:-} OWNER_PASSWORD=${OWNER_PASSWORD:-}" >>"$STUB_CALLS"; sleep 0.5; exit "${STUB_SCALE_EXIT:-0}" ;;
  drive-scaling.sh*) while :; do sleep 0.1; done ;;
esac
EOF
  chmod +x "$repo/scripts/deploy/$script"
done
wrapper=$repo/scripts/deploy/rehearse.sh

# run <case> <arguments...> [-- VAR=value...]: runs the wrapper; sets $status, $out, $calls.
run() {
  local name=$1
  shift
  local args=() vars=()
  while [ $# -gt 0 ] && [ "$1" != -- ]; do args+=("$1"); shift; done
  [ $# -gt 0 ] && shift && vars=("$@")
  local dir="$work/cases/$name"
  mkdir -p "$dir"
  : >"$dir/calls"
  out=$(env PATH="$here/stubs-rehearsal:$PATH" STUB_CALLS="$dir/calls" AWS_SESSION_TOKEN=real-session-token \
    ${vars[@]+"${vars[@]}"} "$wrapper" ${args[@]+"${args[@]}"} 2>&1)
  status=$?
  calls=$(cat "$dir/calls")
}

line() { grep -n -m1 -E -- "$1" <<<"$calls" | cut -d: -f1; }
before() {
  local a b
  a=$(line "$2"); b=$(line "$3")
  if [ -n "$a" ] && [ -n "$b" ] && [ "$a" -lt "$b" ]; then return 0; fi
  fail "$1" "expected '$2' (line ${a:-none}) before '$3' (line ${b:-none})"
  return 1
}
never() { if grep -qE -- "$2" <<<"$calls"; then fail "$1" "unexpected call matching '$2'"; return 1; fi; }
has() { if ! grep -qE -- "$2" <<<"$calls"; then fail "$1" "no call matching '$2' in: $calls"; return 1; fi; }
expect_status() { if [ "$status" != "$2" ]; then fail "$1" "exit $status, expected $2. Output: $out"; return 1; fi; }
expect_output() { if ! grep -qF -- "$2" <<<"$out"; then fail "$1" "expected '$2' in: $out"; return 1; fi; }

compose="docker compose -f $repo/infra/rehearsal/compose.yml"
local_root="DEPLOY_ROOT=$repo/infra/envs/local TF_STATE_BUCKET=studio-local-tfstate"
tools="AWS_ENDPOINT_URL=http://floci:4566 AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_REGION=eu-west-2 AWS_SESSION_TOKEN="

# --- up ---------------------------------------------------------------------------------------------------------------

name=up_runs_the_unchanged_deploy_on_the_local_environment_against_floci
run "$name" up -- STUB_PORT_HOLDERS=dev-floci
ok=1
expect_status $name 0 || ok=0
has $name "^deploy.sh rehearsal 0 amd64 \| $local_root $tools TF_VAR_cpu_architecture=X86_64 REHEARSAL_TOOLS_NETWORK= TF_DATA_DIR=.terraform-rehearsal terraform=$repo/scripts/deploy/rehearsal/terraform$" || ok=0
expect_output $name "The rehearsal is up" || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=up_stops_make_devs_floci_then_starts_the_rehearsals_and_reads_its_ca
ok=1
before $name '^docker stop dev-floci$' "^$compose up -d --wait$" || ok=0
before $name "^$compose up -d --wait$" "^$compose cp floci:/app/data/tls/floci-root-ca.crt .*/floci-root-ca.crt$" || ok=0
expect_output $name "Stopping make dev's Floci, which holds port 4566" || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=up_pulls_the_images_floci_starts_by_name_and_the_front_ends_before_starting_them
ok=1
for image in floci/floci:2.5.0 pgvector/pgvector:0.8.1-pg16 valkey/valkey:7.2 registry:2 node:22.23.5-alpine3.24 hashicorp/terraform:1.14.0 amazon/aws-cli:2.31.0; do
  before $name "^docker pull $image$" "^$compose up" || ok=0
done
never $name '^docker tag' || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=up_builds_the_images_for_this_machine_and_adds_flocis_ca_to_the_backend_image
ok=1
before $name "^make -C $repo images IMAGE_TAG=rehearsal IMAGE_PLATFORM=linux/amd64$" "^docker build -q -f $repo/infra/rehearsal/ca.Dockerfile --build-arg IMAGE=rag-agent-studio/api:rehearsal -t rag-agent-studio/api:rehearsal " || ok=0
has $name "^pnpm build \(in $repo/frontend\)$" || ok=0
before $name "^$compose cp" '^docker build -q -f .*ca.Dockerfile' || ok=0
# The CA file Floci gave is the build context.
grep -qE "^docker build .* (/[^ ]+)$" <<<"$calls" && ctx=$(grep -m1 '^docker build' <<<"$calls" | awk '{print $NF}') &&
  grep -qF "cp floci:/app/data/tls/floci-root-ca.crt $ctx/floci-root-ca.crt" <<<"$calls" || { fail $name "the CA layer is not built from the copied CA"; ok=0; }
before $name '^docker build -q -f .*ca.Dockerfile' '^deploy.sh' || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=up_creates_the_state_bucket_in_the_region_and_installs_the_providers_before_deploying
ok=1
before $name "^aws s3api head-bucket --bucket studio-local-tfstate \| .*$tools" '^aws s3api create-bucket' || ok=0
before $name "^aws s3api create-bucket --bucket studio-local-tfstate --create-bucket-configuration LocationConstraint=eu-west-2 \| .*$tools" '^deploy.sh' || ok=0
before $name "^terraform -chdir=$repo/infra/envs/local init -backend=false -input=false \| .*REHEARSAL_TOOLS_NETWORK=bridge" '^deploy.sh' || ok=0
[ $ok = 1 ] && echo "ok   $name"

# A second rehearsal: the providers step must not try to read the state through the backend the first one configured
# (its network cannot reach Floci). The state itself is in Floci, so only the local note of the backend goes. The
# rehearsal keeps its own Terraform data folder, so that note never reaches `make infra-check`'s .terraform.
name=up_forgets_the_backend_a_previous_rehearsal_configured_before_installing_the_providers
mkdir -p "$repo/infra/envs/local/.terraform-rehearsal/providers" "$repo/infra/envs/local/.terraform"
echo '{"backend":{"type":"s3"}}' >"$repo/infra/envs/local/.terraform-rehearsal/terraform.tfstate"
echo '{"backend":{"type":"s3"}}' >"$repo/infra/envs/local/.terraform/terraform.tfstate"
run "$name" up
ok=1
expect_status $name 0 || ok=0
[ ! -e "$repo/infra/envs/local/.terraform-rehearsal/terraform.tfstate" ] || { fail $name "the previous backend configuration is still there"; ok=0; }
[ -d "$repo/infra/envs/local/.terraform-rehearsal/providers" ] || { fail $name "the installed providers were removed"; ok=0; }
[ -e "$repo/infra/envs/local/.terraform/terraform.tfstate" ] || { fail $name "the wrapper touched .terraform, which is not its own"; ok=0; }
has $name "^terraform -chdir=$repo/infra/envs/local init -backend=false -input=false \| .*TF_DATA_DIR=.terraform-rehearsal " || ok=0
[ $ok = 1 ] && echo "ok   $name"

# Ticket 23-04: a second plan after the apply must show no changes, or emulator drift would hide real drift.
name=up_checks_that_a_second_plan_after_the_apply_shows_no_changes
run "$name" up
ok=1
expect_status $name 0 || ok=0
before $name '^deploy.sh' "^terraform -chdir=$repo/infra/envs/local plan -input=false -detailed-exitcode -var=image_tag=rehearsal \| .*$tools TF_VAR_cpu_architecture=X86_64 REHEARSAL_TOOLS_NETWORK= TF_DATA_DIR=.terraform-rehearsal " || ok=0
expect_output $name "The plan after the apply shows no changes" || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=up_fails_when_the_plan_after_the_apply_shows_changes
run "$name" up -- STUB_PLAN_EXIT=2
ok=1
expect_status $name 1 || ok=0
expect_output $name "The plan after the apply is not empty" || ok=0
expect_output $name "spa_fallback will be updated in-place" || ok=0
grep -qF "The rehearsal is up" <<<"$out" && { fail $name "reported up despite the drift"; ok=0; }
[ $ok = 1 ] && echo "ok   $name"

name=up_fails_when_the_plan_after_the_apply_fails
run "$name" up -- STUB_PLAN_EXIT=1
ok=1
expect_status $name 1 || ok=0
expect_output $name "The plan after the apply failed" || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=up_keeps_an_existing_state_bucket
run "$name" up -- STUB_BUCKET_EXISTS_EXIT=0
ok=1
expect_status $name 0 || ok=0
never $name '^aws s3api create-bucket' || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=up_leaves_the_rehearsals_own_floci_running
run "$name" up -- STUB_PORT_HOLDERS=rehearsal-floci
ok=1
expect_status $name 0 || ok=0
never $name '^docker stop' || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=up_rehearses_arm64_tasks_on_an_arm64_machine
run "$name" up v1.2 -- STUB_MACHINE=arm64
ok=1
expect_status $name 0 || ok=0
has $name "^make -C $repo images IMAGE_TAG=v1.2 IMAGE_PLATFORM=linux/arm64$" || ok=0
has $name "^deploy.sh v1.2 0 arm64 \| .*TF_VAR_cpu_architecture=ARM64 " || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=up_can_use_the_images_already_built
run "$name" up -- REHEARSAL_BUILD=false
ok=1
expect_status $name 0 || ok=0
never $name '^(make|pnpm) ' || ok=0
has $name '^docker build -q -f .*ca.Dockerfile' || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=up_pulls_through_a_docker_hub_mirror_and_tags_the_names_floci_asks_for
run "$name" up -- REHEARSAL_IMAGE_MIRROR=mirror.gcr.io
ok=1
expect_status $name 0 || ok=0
has $name '^docker pull mirror.gcr.io/library/registry:2$' || ok=0
has $name '^docker tag mirror.gcr.io/library/registry:2 registry:2$' || ok=0
has $name '^docker pull mirror.gcr.io/pgvector/pgvector:0.8.1-pg16$' || ok=0
has $name '^docker tag mirror.gcr.io/pgvector/pgvector:0.8.1-pg16 pgvector/pgvector:0.8.1-pg16$' || ok=0
never $name '^docker pull registry:2$' || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=up_fails_clearly_on_a_docker_hub_rate_limit
run "$name" up -- STUB_RATE_LIMITED=valkey/valkey:7.2
ok=1
expect_status $name 1 || ok=0
expect_output $name "Docker Hub refused to pull valkey/valkey:7.2: its rate limit for anonymous pulls is reached" || ok=0
expect_output $name "REHEARSAL_IMAGE_MIRROR" || ok=0
never $name "^$compose up" || ok=0
never $name '^deploy.sh' || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=up_reports_any_other_failed_pull
run "$name" up -- STUB_PULL_FAILS=registry:2
ok=1
expect_status $name 1 || ok=0
expect_output $name "Could not pull registry:2: manifest unknown" || ok=0
never $name "^$compose up" || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=up_says_so_when_docker_does_not_answer_on_its_socket
run "$name" up -- STUB_DOCKER_INFO_EXIT=1
ok=1
expect_status $name 1 || ok=0
expect_output $name "Docker does not answer" || ok=0
expect_output $name "socket" || ok=0
[ "$calls" = "docker info" ] || { fail $name "calls beyond docker info: $calls"; ok=0; }
[ $ok = 1 ] && echo "ok   $name"

name=up_says_so_when_docker_has_too_little_memory
run "$name" up -- STUB_MEMORY=$((6 * 1024 * 1024 * 1024))
ok=1
expect_status $name 1 || ok=0
expect_output $name "Docker has 6 GB of memory, and the rehearsal needs at least 8 GB" || ok=0
never $name '^docker (stop|pull|compose)' || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=up_refuses_an_unknown_machine_architecture
run "$name" up -- STUB_MACHINE=riscv64
ok=1
expect_status $name 1 || ok=0
expect_output $name "Unsupported machine architecture riscv64" || ok=0
never $name '^docker (stop|pull|compose)' || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=up_fails_when_the_deploy_fails
run "$name" up -- STUB_DEPLOY_EXIT=1
ok=1
expect_status $name 1 || ok=0
grep -qF "The rehearsal is up" <<<"$out" && { fail $name "reported up after a failed deploy"; ok=0; }
[ $ok = 1 ] && echo "ok   $name"

for args in "" "sideways" "up latest" "up a b" "down now" "up has/slash" "seed now" "seed --reset x"; do
  name="rejects_the_arguments_'$args'"
  # shellcheck disable=SC2086 # Split into arguments on purpose.
  run "$name" $args
  ok=1
  expect_status "$name" 2 || ok=0
  [ -z "$calls" ] || { fail "$name" "calls were made: $calls"; ok=0; }
  [ $ok = 1 ] && echo "ok   $name"
done

# --- seed (ticket 23-04) ----------------------------------------------------------------------------------------------

name=seed_runs_the_unchanged_seed_script_on_the_local_environment
run "$name" seed
ok=1
expect_status $name 0 || ok=0
has $name "^seed.sh  \| $local_root $tools TF_VAR_cpu_architecture= REHEARSAL_TOOLS_NETWORK= TF_DATA_DIR=.terraform-rehearsal terraform=$repo/scripts/deploy/rehearsal/terraform$" || ok=0
never $name '^(deploy|destroy).sh|^docker (stop|pull|compose)' || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=seed_passes_reset_on
run "$name" seed --reset
ok=1
expect_status $name 0 || ok=0
has $name '^seed.sh --reset \| ' || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=seed_fails_when_the_seed_fails
run "$name" seed -- STUB_SEED_EXIT=1
ok=1
expect_status $name 1 || ok=0
[ $ok = 1 ] && echo "ok   $name"

# --- scale (ticket 23-05) ---------------------------------------------------------------------------------------------

name=scale_runs_the_unchanged_scaling_script_on_the_seeded_rehearsal_with_laptop_sized_load
run "$name" scale
ok=1
expect_status $name 0 || ok=0
has $name "^terraform -chdir=$repo/infra/envs/local init -input=false -backend-config=bucket=studio-local-tfstate -backend-config=region=eu-west-2 \| $local_root $tools " || ok=0
has $name "^scale.sh --copies 4 --runs 1 --api-seconds 240 --api-workers 8 --poll-seconds 15 --timeout-minutes 30 http://e1.cloudfront.localhost:4566 \| $local_root $tools .*terraform=$repo/scripts/deploy/rehearsal/terraform$" || ok=0
has $name "^scale.sh OWNER_EMAIL=owner@northwind.example OWNER_PASSWORD=northwind-owner-demo$" || ok=0
never $name '^(deploy|destroy|seed).sh|^docker (stop|pull|compose)' || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=scale_publishes_the_figures_floci_does_not_compute_while_the_script_runs_and_stops_after
ok=1
before $name "^terraform .* output -raw jobs_metric_namespace" '^drive-scaling.sh ' || ok=0
has $name '^drive-scaling.sh studio-local-ecs studio-local-ecs-api studio-local-queue-general studio-local-queue-runs Rehearsal/SQS \| ' || ok=0
pgrep -f "$repo/scripts/deploy/rehearsal/drive-scaling.sh" >/dev/null && { fail $name "the driver is still running"; ok=0; }
[ $ok = 1 ] && echo "ok   $name"

name=scale_passes_options_through_and_they_win_over_the_defaults
run "$name" scale --copies 4 --timeout-minutes 45 -- OWNER_EMAIL=me@example.com OWNER_PASSWORD=secret
ok=1
expect_status $name 0 || ok=0
has $name "^scale.sh --copies 4 --runs 1 --api-seconds 240 --api-workers 8 --poll-seconds 15 --timeout-minutes 30 --copies 4 --timeout-minutes 45 http://e1.cloudfront.localhost:4566 \| " || ok=0
has $name "^scale.sh OWNER_EMAIL=me@example.com OWNER_PASSWORD=secret$" || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=scale_fails_when_a_service_never_scaled
run "$name" scale -- STUB_SCALE_EXIT=1
ok=1
expect_status $name 1 || ok=0
pgrep -f "$repo/scripts/deploy/rehearsal/drive-scaling.sh" >/dev/null && { fail $name "the driver is still running"; ok=0; }
[ $ok = 1 ] && echo "ok   $name"

# --- down -------------------------------------------------------------------------------------------------------------

name=down_destroys_the_local_environment_then_removes_floci_and_its_data
run "$name" down -- STUB_FLOCI_RUNNING=1 STUB_FLOCI_CONTAINERS="db1 task1" STUB_FLOCI_VOLUMES="floci-aws-ecr-registry-data floci-aws-rds-db-1"
ok=1
expect_status $name 0 || ok=0
has $name "^destroy.sh destroy demo \| $local_root $tools " || ok=0
before $name '^destroy.sh' "^$compose down --volumes --remove-orphans$" || ok=0
before $name "^$compose down" '^docker rm -f db1 task1$' || ok=0
has $name '^docker volume rm -f floci-aws-ecr-registry-data floci-aws-rds-db-1$' || ok=0
expect_output $name "The rehearsal is removed" || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=down_without_a_running_floci_only_removes_what_is_left
run "$name" down
ok=1
expect_status $name 0 || ok=0
never $name '^destroy.sh' || ok=0
has $name "^$compose down --volumes --remove-orphans$" || ok=0
never $name '^docker (rm|volume rm)' || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=down_still_removes_floci_when_the_destroy_fails
run "$name" down -- STUB_FLOCI_RUNNING=1 STUB_DESTROY_EXIT=1
ok=1
expect_status $name 0 || ok=0
expect_output $name "The destroy did not finish" || ok=0
has $name "^$compose down --volumes --remove-orphans$" || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=down_says_so_when_docker_does_not_answer
run "$name" down -- STUB_DOCKER_INFO_EXIT=1
ok=1
expect_status $name 1 || ok=0
expect_output $name "Docker does not answer" || ok=0
[ $ok = 1 ] && echo "ok   $name"

# --- run-tool.sh: terraform and the AWS CLI reach only Floci ----------------------------------------------------------

# tool <case> <shim> <arguments...>: runs the real shim with the docker stub; sets $status and $calls.
tool() {
  local name=$1 shim=$2
  shift 2
  local dir="$work/cases/$name"
  mkdir -p "$dir"
  : >"$dir/calls"
  (cd "$work" && env PATH="$here/stubs-rehearsal:$PATH" STUB_CALLS="$dir/calls" AWS_ENDPOINT_URL=http://floci:4566 \
    AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_REGION=eu-west-2 AWS_SESSION_TOKEN=real-session-token \
    GITHUB_TOKEN=a-secret TF_VAR_cpu_architecture=ARM64 TF_DATA_DIR=.terraform-rehearsal "$@" "$here/../rehearsal/$shim" -chdir=/somewhere plan) >/dev/null 2>&1
  status=$?
  calls=$(cat "$dir/calls")
}

name=terraform_runs_in_a_container_on_the_tools_network_with_only_the_rehearsals_settings
tool "$name" terraform
ok=1
expect_status $name 0 || ok=0
repo_root=$(cd "$here/../../.." && pwd)
has $name "^docker run --rm -i --network studio-rehearsal-tools -u $(id -u):$(id -g) -v $repo_root:$repo_root -v ${TMPDIR:-/tmp}:${TMPDIR:-/tmp} -w $work " || ok=0
for setting in AWS_ENDPOINT_URL AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_REGION TF_VAR_cpu_architecture TF_DATA_DIR; do
  has $name " -e $setting " || ok=0
done
never $name 'AWS_SESSION_TOKEN|GITHUB_TOKEN' || ok=0
has $name ' --entrypoint terraform hashicorp/terraform:1.14.0 -chdir=/somewhere plan$' || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=the_aws_cli_runs_in_a_container_on_the_tools_network
tool "$name" aws
ok=1
has $name '^docker run --rm -i --network studio-rehearsal-tools ' || ok=0
has $name ' --entrypoint aws amazon/aws-cli:2.31.0 -chdir=/somewhere plan$' || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=the_tools_network_image_and_extra_docker_arguments_can_be_given
tool "$name" terraform REHEARSAL_TOOLS_NETWORK=bridge REHEARSAL_TERRAFORM_IMAGE=example/terraform:1 REHEARSAL_TOOLS_DOCKER_ARGS="-v /mirror:/mirror:ro -e TF_CLI_CONFIG_FILE=/mirror/rc"
ok=1
has $name '^docker run --rm -i --network bridge ' || ok=0
has $name ' -v /mirror:/mirror:ro -e TF_CLI_CONFIG_FILE=/mirror/rc --entrypoint terraform example/terraform:1 ' || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=run_tool_refuses_another_tool
out=$("$here/../rehearsal/run-tool.sh" curl 2>&1)
status=$?
ok=1
expect_status $name 2 || ok=0
expect_output $name "usage:" || ok=0
[ $ok = 1 ] && echo "ok   $name"

exit $((failures > 0))
