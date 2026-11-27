#!/usr/bin/env bash
# Rehearses the AWS deployment on this machine against Floci, an AWS emulator, with no AWS account (spec 23, ticket
# 23-03). `make rehearse` runs `up`, `make rehearse-seed` runs `seed`, `make rehearse-scale` runs `scale` and
# `make rehearse-down` runs `down`.
#
# up [image tag, default rehearsal]:
#   1. checks Docker answers on its socket and has the memory the stack needs
#   2. stops `make dev`'s Floci (it holds port 4566, which the emulator must use) and pulls the images Floci starts by
#      name, failing clearly on a Docker Hub rate limit
#   3. starts Floci and its front end (infra/rehearsal/compose.yml) and reads Floci's root CA. The front end publishes
#      Floci's port and runs the Studio's SPA fallback CloudFront Function, which Floci stores but does not run, so
#      deep links load the Studio and the API's 404s stay the API's (ticket 23-04)
#   4. builds the images (`make images`, for this machine's architecture) and the frontend (`pnpm build`), then adds
#      Floci's CA to the backend image (infra/rehearsal/ca.Dockerfile)
#   5. points terraform and the AWS CLI at Floci: they run in containers on a network that reaches only Floci
#      (scripts/deploy/rehearsal), with the endpoint, dummy credentials and region exported here
#   6. creates the state bucket in Floci, in the region, and installs the providers
#   7. runs the unchanged scripts/deploy/deploy.sh on the local environment (infra/envs/local), which applies it, pushes
#      the images, migrates, rolls the services, uploads the Studio and smoke-checks the emulated distribution
#   8. plans again and fails unless the plan shows no changes, so emulator drift cannot hide real drift (ticket 23-04)
# seed [--reset]: runs the unchanged scripts/deploy/seed.sh on the local environment: the seed as a one-off task, which
#   prints the demo sign-in details (ticket 23-04).
# scale [scale.sh options]: runs the unchanged scripts/deploy/scale.sh on the seeded rehearsal with a load sized for a
#   laptop (options given here win), while scripts/deploy/rehearsal/drive-scaling.sh publishes what Floci does not
#   compute: each pool's queue jobs, the metric local's pool alarms watch, and the API's CPU (ticket 23-05). It exits
#   non-zero, naming the service, if a service never scaled out or did not return to its minimum.
# down: destroys the local environment through the unchanged scripts/deploy/destroy.sh, then removes Floci, the
#   containers and volumes it started, and its data. `make dev`'s Floci is not restarted (`make services` does that).
#
# Optional: REHEARSAL_BUILD=false (use the images and frontend builds already here), REHEARSAL_IMAGE_MIRROR (a Docker Hub
# mirror to pull from, such as mirror.gcr.io), REHEARSAL_MIN_MEMORY_GB (default 8), REHEARSAL_ARCH (amd64 or arm64;
# default this machine's), and run-tool.sh's REHEARSAL_TOOLS_* settings.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
compose_file=$repo/infra/rehearsal/compose.yml
root=$repo/infra/envs/local
region=eu-west-2
state_bucket=studio-local-tfstate
data_dir=.terraform-rehearsal

usage() { echo "usage: $0 up [image tag, default rehearsal] | seed [--reset] | scale [scale.sh options] | down" >&2; exit 2; }
command=${1:-}
case "$#:$command:${2:-}" in
  1:up: | 2:up:* | 1:down: | 1:seed: | 2:seed:--reset | *:scale:*) ;;
  *) usage ;;
esac
tag=rehearsal
if [ "$command" = up ]; then
  tag=${2:-rehearsal}
  [[ "$tag" =~ ^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$ ]] && [ "$tag" != latest ] || usage
fi

step() { echo "==> $*"; }
die() { echo "::error title=Rehearsal failed::$*" >&2; exit 1; }
compose() { docker compose -f "$compose_file" "$@"; }

# --- 1. Docker ------------------------------------------------------------------------------------------------------
if ! docker info >/dev/null 2>&1; then
  die "Docker does not answer. Start Docker, and make sure this user may use its socket (Linux: add yourself to the docker group, or set DOCKER_HOST); Floci needs the socket to start the database, cache, registry and tasks."
fi

# The emulator, the tools and the images Floci starts, by name. A mirror is a Docker Hub mirror (Docker Hub limits
# anonymous pulls); each image pulled from it is tagged with the name Floci asks for.
# The front end (node) runs the Studio's SPA fallback function in front of Floci (ticket 23-04).
images=(floci/floci:2.5.0 pgvector/pgvector:0.8.1-pg16 valkey/valkey:7.2 registry:2 node:22.23.5-alpine3.24
  "${REHEARSAL_TERRAFORM_IMAGE:-hashicorp/terraform:1.14.0}" "${REHEARSAL_AWS_IMAGE:-amazon/aws-cli:2.31.0}")
pull() {
  local image=$1 source=$1 output
  if [ -n "${REHEARSAL_IMAGE_MIRROR:-}" ]; then
    [[ "$image" == */* ]] && source="$REHEARSAL_IMAGE_MIRROR/$image" || source="$REHEARSAL_IMAGE_MIRROR/library/$image"
  fi
  if ! output=$(docker pull "$source" 2>&1); then
    if grep -qiE 'toomanyrequests|rate limit' <<<"$output"; then
      die "Docker Hub refused to pull $source: its rate limit for anonymous pulls is reached. Log in with \`docker login\`, wait, or pull through a mirror with REHEARSAL_IMAGE_MIRROR (for example mirror.gcr.io)."
    fi
    die "Could not pull $source: $output"
  fi
  [ "$source" = "$image" ] || docker tag "$source" "$image"
}

# Floci labels every container it starts (database, cache, registry, tasks) floci=true.
remove_floci_containers() {
  local ids
  ids=$(docker ps -aq --filter label=floci=true)
  # shellcheck disable=SC2086 # One argument per container.
  [ -z "$ids" ] || docker rm -f $ids >/dev/null
}

# The tools' view of Floci (they run on the tools network), the dummy credentials and the region. Floci checks no
# credentials; these only keep the SDKs from looking for real ones.
point_tools_at_floci() {
  export PATH="$here/rehearsal:$PATH"
  export AWS_ENDPOINT_URL=http://floci:4566 AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test
  export AWS_REGION=$region AWS_DEFAULT_REGION=$region
  unset AWS_SESSION_TOKEN AWS_PROFILE
  export DEPLOY_ROOT=$root TF_STATE_BUCKET=$state_bucket
  # The rehearsal's own Terraform data folder (in infra/envs/local), so the backend it configures never reaches the
  # .terraform folder that `make infra-check` and other plain terraform runs use.
  export TF_DATA_DIR=$data_dir
}

if [ "$command" = seed ]; then
  point_tools_at_floci
  exec "$here/seed.sh" ${2:+"$2"}
fi

if [ "$command" = scale ]; then
  shift
  point_tools_at_floci
  terraform -chdir="$root" init -input=false "-backend-config=bucket=$state_bucket" "-backend-config=region=$region" >/dev/null
  work=$(mktemp -d)
  terraform -chdir="$root" output -json deploy >"$work/deploy.json"
  namespace=$(terraform -chdir="$root" output -raw jobs_metric_namespace)
  out() { jq -r "$1" "$work/deploy.json"; }
  "$here/rehearsal/drive-scaling.sh" "$(out .cluster_name)" "$(out .services.api)" "$(out .queue_names.general)" \
    "$(out .queue_names.runs)" "$namespace" >"$work/drive.log" 2>&1 &
  driver=$!
  trap 'kill "$driver" 2>/dev/null; wait "$driver" 2>/dev/null || true; cat "$work/drive.log"; rm -rf "$work"' EXIT
  step "Publishing each pool's queue jobs and the API's CPU to Floci's CloudWatch while the scaling script runs"
  # The demo Owner's published sign-in (backend/app/seed/content.py). A laptop-sized load: 4 copies of each seed
  # Document, one Run, four minutes of API requests, a row every 15 seconds.
  export OWNER_EMAIL=${OWNER_EMAIL:-owner@northwind.example} OWNER_PASSWORD=${OWNER_PASSWORD:-northwind-owner-demo}
  export AWS_REGION=$region
  status=0
  "$here/scale.sh" --copies 4 --runs 1 --api-seconds 240 --api-workers 8 --poll-seconds 15 --timeout-minutes 30 "$@" \
    "$(out .cloudfront_url)" || status=$?
  exit "$status"
fi

if [ "$command" = down ]; then
  if [ -n "$(compose ps -q floci 2>/dev/null)" ]; then
    point_tools_at_floci
    step "Destroying the local environment"
    # destroy.sh asks for the demo destroy workflow's confirmation phrase; the root it destroys is DEPLOY_ROOT.
    "$here/destroy.sh" "destroy demo" || echo "The destroy did not finish; everything it made lives in Floci, which is removed next."
  fi
  step "Removing Floci, the containers it started and its data"
  compose down --volumes --remove-orphans
  remove_floci_containers
  volumes=$(docker volume ls -q --filter name=floci-aws-) || true
  # shellcheck disable=SC2086 # One argument per volume.
  [ -z "$volumes" ] || docker volume rm -f $volumes >/dev/null
  echo "The rehearsal is removed. \`make services\` starts make dev's Floci again."
  exit 0
fi

# The stack peaks at about 8 GB (ticket 23-01); Floci enforces each task's memory as a hard limit.
min_gb=${REHEARSAL_MIN_MEMORY_GB:-8}
memory=$(docker info --format '{{.MemTotal}}')
if [ "$memory" -lt $((min_gb * 1024 * 1024 * 1024)) ]; then
  die "Docker has $((memory / 1024 / 1024 / 1024)) GB of memory, and the rehearsal needs at least $min_gb GB (the API and each worker task take up to 3 GB). Give Docker more memory (Docker Desktop: Settings, Resources)."
fi

case "${REHEARSAL_ARCH:-$(uname -m)}" in
  x86_64 | amd64) arch=amd64 cpu_architecture=X86_64 ;;
  arm64 | aarch64) arch=arm64 cpu_architecture=ARM64 ;;
  *) die "Unsupported machine architecture $(uname -m): the rehearsal runs on x86_64 (Intel) and arm64 (Apple silicon) machines." ;;
esac

# --- 2. Port 4566 and images ----------------------------------------------------------------------------------------
for id in $(docker ps -q --filter label=com.docker.compose.service=floci --filter publish=4566); do
  if [ "$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' "$id")" != studio-rehearsal ]; then
    step "Stopping make dev's Floci, which holds port 4566"
    docker stop "$id" >/dev/null
  fi
done
step "Pulling the emulator's images"
for image in "${images[@]}"; do pull "$image"; done

# --- 3. Floci -------------------------------------------------------------------------------------------------------
step "Starting Floci and its front end"
compose up -d --wait
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
compose cp floci:/app/data/tls/floci-root-ca.crt "$work/floci-root-ca.crt"

# --- 4. Images ------------------------------------------------------------------------------------------------------
if [ "${REHEARSAL_BUILD:-true}" != false ]; then
  step "Building the images for linux/$arch and the frontend"
  make -C "$repo" images IMAGE_TAG="$tag" IMAGE_PLATFORM="linux/$arch"
  (cd "$repo/frontend" && pnpm build)
fi
step "Adding Floci's CA to rag-agent-studio/api:$tag"
docker build -q -f "$repo/infra/rehearsal/ca.Dockerfile" --build-arg "IMAGE=rag-agent-studio/api:$tag" \
  -t "rag-agent-studio/api:$tag" "$work" >/dev/null

# --- 5 and 6. Tools, state bucket, providers ------------------------------------------------------------------------
point_tools_at_floci
export TF_VAR_cpu_architecture=$cpu_architecture
if ! aws s3api head-bucket --bucket "$state_bucket" >/dev/null 2>&1; then
  step "Creating the state bucket $state_bucket in Floci"
  # A bucket outside us-east-1 needs its location constraint; Floci refuses a bare create (ticket 23-01).
  aws s3api create-bucket --bucket "$state_bucket" --create-bucket-configuration "LocationConstraint=$region" >/dev/null
fi
# The tools network has no route out, so the providers are installed first from the default network; deploy.sh's
# init then finds them in place. That network cannot reach Floci, so the note of the backend a previous rehearsal
# configured goes first (the state itself is in Floci); deploy.sh's init configures it again.
step "Installing the Terraform providers"
rm -f "$root/$data_dir/terraform.tfstate"
REHEARSAL_TOOLS_NETWORK=bridge terraform -chdir="$root" init -backend=false -input=false >/dev/null

# --- 7. The unchanged deploy ----------------------------------------------------------------------------------------
# No old worker task can be running a job in a fresh rehearsal, so the roll does not wait (0 minutes).
"$here/deploy.sh" "$tag" 0 "$arch"

# --- 8. No drift ----------------------------------------------------------------------------------------------------
# Every difference the emulator causes is an input of the local environment (ticket 23-04); a change here is new drift.
step "Planning again: the plan after the apply must show no changes"
plan_status=0
terraform -chdir="$root" plan -input=false -detailed-exitcode "-var=image_tag=$tag" >"$work/plan.txt" 2>&1 || plan_status=$?
case "$plan_status" in
  0) echo "The plan after the apply shows no changes." ;;
  2) cat "$work/plan.txt"; die "The plan after the apply is not empty (above): the emulator reads something back differently. Give infra/envs/local an input for it rather than ignoring it." ;;
  *) cat "$work/plan.txt"; die "The plan after the apply failed (above)." ;;
esac
echo "The rehearsal is up. \`make rehearse-seed\` seeds the demo Organisation; \`make rehearse-down\` removes it."
