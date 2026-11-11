#!/usr/bin/env bash
# Brings the demo environment up at an image tag (spec 09 stories 25, 26 and 32). The deploy workflow runs it; it
# also runs by hand with AWS credentials for the account. In order:
#   1. terraform init against the bootstrap's state bucket, and apply the ECR repositories (a first run creates them)
#   2. push the API and Studio images at the tag (built for arm64), unless ECR already has the tag
#   3. terraform apply at the tag: new task definitions for the services and the migration task (the services
#      themselves do not roll on apply; see the ecs module)
#   4. run the migration task (`alembic upgrade head`) and wait for it; anything but exit 0 stops the deploy here
#   5. point each service at its new task definition and wait until all of them are stable
#   6. upload the Studio and widget builds and the demo pages (under /demo/) to the static bucket; HTML, embed.js and
#      the unhashed widget.js no-cache
#   7. invalidate those paths in CloudFront and wait for the invalidation
#   8. smoke check the CloudFront URL (scripts/deploy/smoke.sh) and print it
# Usage: TF_STATE_BUCKET=... AWS_REGION=... scripts/deploy/deploy.sh <image tag>
# Optional: DEPLOY_ROOT (default infra/envs/demo), STUDIO_DIST and WIDGET_DIST (the `pnpm build` outputs), DEMO_DIST
# (the demo pages, default frontend/apps/widget/host/demo; the disallowed-origin page beside it is local-only),
# SMOKE_AGENT_ID (a live Agent's public ID for the widget shell check), SMOKE_ATTEMPTS, SMOKE_DELAY_SECONDS.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)

usage() { echo "usage: $0 <image tag> (1-128 of A-Z a-z 0-9 . _ -, not latest)" >&2; exit 2; }
[ $# -eq 1 ] || usage
tag=$1
[[ "$tag" =~ ^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$ ]] && [ "$tag" != latest ] || usage
[ -n "${TF_STATE_BUCKET:-}" ] || { echo "TF_STATE_BUCKET must name the bootstrap's state bucket (its state_bucket_name output)." >&2; exit 2; }
[ -n "${AWS_REGION:-}" ] || { echo "AWS_REGION must be set." >&2; exit 2; }
root=${DEPLOY_ROOT:-$repo/infra/envs/demo}
studio_dist=${STUDIO_DIST:-$repo/frontend/apps/studio/dist}
widget_dist=${WIDGET_DIST:-$repo/frontend/apps/widget/dist}
demo_dist=${DEMO_DIST:-$repo/frontend/apps/widget/host/demo}
for f in "$studio_dist/index.html" "$widget_dist/embed.js" "$widget_dist/widget/assets/widget.js"; do
  [ -f "$f" ] || { echo "$f is missing: run \`pnpm build\` in frontend/ first." >&2; exit 2; }
done
[ -f "$demo_dist/index.html" ] || { echo "$demo_dist/index.html is missing: DEMO_DIST must hold the demo pages." >&2; exit 2; }

step() { echo "==> $*"; }
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# --- 1. State and registries ---------------------------------------------------------------------------------------
step "terraform init (state bucket $TF_STATE_BUCKET)"
terraform -chdir="$root" init -input=false -backend-config="bucket=$TF_STATE_BUCKET" -backend-config="region=$AWS_REGION"
step "Making sure the ECR repositories exist"
terraform -chdir="$root" apply -input=false -auto-approve -target=module.ecr

# --- 2. Images -------------------------------------------------------------------------------------------------------
registry="$(aws sts get-caller-identity --query Account --output text).dkr.ecr.$AWS_REGION.amazonaws.com"
if aws ecr describe-images --repository-name rag-agent-studio/api --image-ids "imageTag=$tag" >/dev/null 2>&1; then
  step "rag-agent-studio/api:$tag is already in ECR"
else
  if ! arch=$(docker image inspect --format '{{.Architecture}}' "rag-agent-studio/api:$tag" 2>/dev/null); then
    echo "::error title=No image::rag-agent-studio/api:$tag is not in ECR and was not built here. Deploy a pushed tag, or build it first (make images IMAGE_TAG=$tag IMAGE_PLATFORM=linux/arm64)." >&2
    exit 1
  fi
  # The tasks run on ARM64 Fargate (ADR-0010); an x86 image would fail to start with "exec format error".
  if [ "$arch" != arm64 ]; then
    echo "::error title=Wrong architecture::rag-agent-studio/api:$tag is built for $arch, but the tasks run on arm64. Build it with IMAGE_PLATFORM=linux/arm64." >&2
    exit 1
  fi
  step "Pushing the images at $tag to $registry"
  aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$registry"
  for image in api studio; do
    docker tag "rag-agent-studio/$image:$tag" "$registry/rag-agent-studio/$image:$tag"
    docker push "$registry/rag-agent-studio/$image:$tag"
  done
fi

# --- 3. Apply at the tag ---------------------------------------------------------------------------------------------
step "terraform apply at image tag $tag"
terraform -chdir="$root" apply -input=false -auto-approve "-var=image_tag=$tag"
terraform -chdir="$root" output -json deploy >"$work/deploy.json"
out() { jq -r "$1" "$work/deploy.json"; }
cluster=$(out .cluster_name)

# --- 4. Migrations ---------------------------------------------------------------------------------------------------
step "Running the migration task"
network="awsvpcConfiguration={subnets=[$(out '.migration_task.subnet_ids | join(",")')],securityGroups=[$(out .migration_task.security_group_id)],assignPublicIp=DISABLED}"
task=$(aws ecs run-task --cluster "$cluster" --task-definition "$(out .migration_task.task_definition_arn)" \
  --launch-type FARGATE --started-by "deploy-$tag" --network-configuration "$network" \
  --query 'tasks[0].taskArn' --output text)
if [[ "$task" != arn:* ]]; then
  echo "::error title=Migration failed::The migration task did not start ($task). Services were not updated." >&2
  exit 1
fi
aws ecs wait tasks-stopped --cluster "$cluster" --tasks "$task"
exit_code=$(aws ecs describe-tasks --cluster "$cluster" --tasks "$task" \
  --query "tasks[0].containers[?name==\`$(out .migration_task.container_name)\`].exitCode | [0]" --output text)
if [ "$exit_code" != 0 ]; then
  echo "::error title=Migration failed::Migration task exited $exit_code ($task); see its log group. Services were not updated." >&2
  exit 1
fi

# --- 5. Roll the services --------------------------------------------------------------------------------------------
services=()
for key in $(out '.services | keys[]'); do
  service=$(out ".services.$key")
  services+=("$service")
  step "Rolling $service onto $(out ".task_definition_arns.$key")"
  aws ecs update-service --cluster "$cluster" --service "$service" --task-definition "$(out ".task_definition_arns.$key")" \
    --query service.serviceName --output text >/dev/null
done
step "Waiting for ${services[*]} to stabilise"
if ! aws ecs wait services-stable --cluster "$cluster" --services "${services[@]}"; then
  echo "::error title=Rollout failed::${services[*]} did not stabilise. The deployment circuit breaker rolls a failing service back; see the services' events and log groups." >&2
  exit 1
fi

# --- 6. Static assets ------------------------------------------------------------------------------------------------
bucket=$(out .static_bucket_name)
step "Uploading the Studio and widget builds and the demo pages to $bucket"
mkdir -p "$work/static/demo"
cp -R "$studio_dist/." "$work/static/"
cp -R "$widget_dist/." "$work/static/"
cp -R "$demo_dist/." "$work/static/demo/"
# Unhashed entry points (and the demo pages) are revalidated on every load; everything else is content-hashed and
# cached for a year.
no_cache=(index.html embed.js widget/assets/widget.js)
for f in "$work/static/demo/"*.html; do no_cache+=("demo/$(basename "$f")"); done
excludes=()
for f in "${no_cache[@]}"; do excludes+=(--exclude "$f"); done
aws s3 sync "$work/static" "s3://$bucket" --delete --cache-control public,max-age=31536000,immutable "${excludes[@]}"
for f in "${no_cache[@]}"; do
  aws s3 cp "$work/static/$f" "s3://$bucket/$f" --cache-control no-cache
done

# --- 7. Invalidate ---------------------------------------------------------------------------------------------------
distribution=$(out .cloudfront_distribution_id)
step "Invalidating the HTML, the loader and the demo pages in $distribution"
invalidation=$(aws cloudfront create-invalidation --distribution-id "$distribution" \
  --paths / /index.html /embed.js /widget/assets/widget.js '/demo/*' --query Invalidation.Id --output text)
aws cloudfront wait invalidation-completed --distribution-id "$distribution" --id "$invalidation"

# --- 8. Smoke check --------------------------------------------------------------------------------------------------
url=$(out .cloudfront_url)
step "Smoke checking $url"
"$here/smoke.sh" "$url" ${SMOKE_AGENT_ID:+"$SMOKE_AGENT_ID"}
echo "Deployed $tag: $url"
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  # shellcheck disable=SC2016 # The backticks are Markdown.
  printf '### Demo deployed\n\n- Image tag: `%s`\n- URL: %s\n' "$tag" "$url" >>"$GITHUB_STEP_SUMMARY"
fi
