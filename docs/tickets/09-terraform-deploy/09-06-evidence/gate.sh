#!/usr/bin/env bash
# shellcheck disable=SC2016,SC2329 # Literal code snippets in single quotes; functions called from traps or loops.
# Applies single regressions to a throwaway copy of the repository, one at a time, and shows that the tests catch
# each one (the suite must exit non-zero). Usage, from the repository root:
#   docs/tickets/09-terraform-deploy/09-06-evidence/gate.sh > docs/tickets/09-terraform-deploy/09-06-evidence/gate-demo.log
set -uo pipefail
repo=$(pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
caught=0 missed=0

# mutate <name> <file> <python expression old> <new> <test command...>
mutate() {
  local name=$1 file=$2 old=$3 new=$4 copy status
  shift 4
  copy="$work/$name"
  mkdir -p "$copy"
  git -C "$repo" ls-files -z | (cd "$repo" && xargs -0 cp --parents -t "$copy")
  if ! OLD=$old NEW=$new python3 -I -c 'import os,sys; p=sys.argv[1]; s=open(p).read(); o=os.environ["OLD"]; assert s.count(o)==1, "pattern not found once"; open(p,"w").write(s.replace(o,os.environ["NEW"]))' "$copy/$file"; then
    echo "SETUP FAILED $name"; missed=$((missed + 1)); return
  fi
  (cd "$copy" && "$@") >"$work/$name.out" 2>&1
  status=$?
  if [ "$status" != 0 ]; then
    echo "caught  $name (exit $status): $(grep -m1 -E 'FAIL|Error:|error_message|fail$' "$work/$name.out" | head -c 200)"
    caught=$((caught + 1))
  else
    echo "MISSED  $name"; missed=$((missed + 1))
  fi
  rm -rf "$copy"
}

tf() { terraform -chdir="$1" init -backend=false -input=false -no-color >/dev/null && terraform -chdir="$1" test -no-color; }

# --- Terraform: the migration task and the demo wiring ----------------------------------------------------------------
mutate ecs_migration_runs_another_command infra/modules/ecs/migrate.tf '["alembic", "upgrade", "head"]' '["alembic", "current"]' tf infra/modules/ecs
mutate ecs_migration_gets_the_redis_token infra/modules/ecs/migrate.tf 'migrate_secrets     = merge({ DATABASE_PASSWORD = var.database.password_secret_arn }' 'migrate_secrets     = merge({ DATABASE_PASSWORD = var.database.password_secret_arn, REDIS_AUTH_TOKEN = var.cache.auth_token_secret_arn }' tf infra/modules/ecs
mutate ecs_migration_reaches_redis infra/modules/ecs/migrate.tf '    postgres = { port = var.database.port, cidr = null, security_group = var.database.security_group_id }' '    postgres = { port = var.database.port, cidr = null, security_group = var.database.security_group_id }
    redis    = { port = var.cache.port, cidr = null, security_group = var.cache.security_group_id }' tf infra/modules/ecs
mutate ecs_migration_reuses_the_api_task_role infra/modules/ecs/migrate.tf 'task_role_arn            = aws_iam_role.migrate_task.arn' 'task_role_arn            = aws_iam_role.task["api"].arn' tf infra/modules/ecs
mutate ecs_migration_runs_in_public_subnets infra/modules/ecs/outputs.tf 'subnet_ids          = var.private_subnet_ids' 'subnet_ids          = var.public_subnet_ids' tf infra/modules/ecs
mutate demo_database_does_not_admit_migrations infra/envs/demo/main.tf '    { migrate = module.ecs.migration_security_group_id },' '' tf infra/envs/demo
mutate demo_deploy_output_lacks_the_bucket infra/envs/demo/outputs.tf '    static_bucket_name         = module.storage.static_bucket_name' '    static_bucket_name         = module.storage.documents_bucket_name' tf infra/envs/demo
mutate demo_deploy_output_has_a_stale_tag infra/envs/demo/outputs.tf '    image_tag                  = var.image_tag' '    image_tag                  = "bootstrap"' tf infra/envs/demo

# --- Composition ------------------------------------------------------------------------------------------------------
mutate demo_drops_the_cdn infra/envs/demo/main.tf 'source                             = "../../modules/cdn"' 'source                             = "../../modules/cdn-old"' infra/tests/compose.test.sh

# --- Deploy script ----------------------------------------------------------------------------------------------------
mutate deploy_ignores_a_failed_migration scripts/deploy/deploy.sh 'if [ "$exit_code" != 0 ]; then' 'if false; then' scripts/deploy/tests/deploy.test.sh
mutate deploy_does_not_wait_for_the_migration scripts/deploy/deploy.sh 'aws ecs wait tasks-stopped --cluster "$cluster" --tasks "$task"' 'true' scripts/deploy/tests/deploy.test.sh
mutate deploy_does_not_wait_for_stable_services scripts/deploy/deploy.sh 'if ! aws ecs wait services-stable --cluster "$cluster" --services "${services[@]}"; then' 'if false; then' scripts/deploy/tests/deploy.test.sh
mutate deploy_skips_the_smoke_check scripts/deploy/deploy.sh '"$here/smoke.sh" "$url" ${SMOKE_AGENT_ID:+"$SMOKE_AGENT_ID"}' 'true' scripts/deploy/tests/deploy.test.sh
mutate deploy_does_not_invalidate_the_loader scripts/deploy/deploy.sh '--paths / /index.html /embed.js /widget/assets/widget.js' '--paths / /index.html' scripts/deploy/tests/deploy.test.sh
mutate deploy_caches_widget_js_for_a_year scripts/deploy/deploy.sh 'no_cache=(index.html embed.js widget/assets/widget.js)' 'no_cache=(index.html embed.js)' scripts/deploy/tests/deploy.test.sh
mutate deploy_uploads_only_the_studio scripts/deploy/deploy.sh 'cp -R "$widget_dist/." "$work/static/"' 'true' scripts/deploy/tests/deploy.test.sh
mutate deploy_runs_migrations_with_a_public_ip scripts/deploy/deploy.sh 'assignPublicIp=DISABLED' 'assignPublicIp=ENABLED' scripts/deploy/tests/deploy.test.sh
mutate deploy_accepts_latest scripts/deploy/deploy.sh '&& [ "$tag" != latest ]' '' scripts/deploy/tests/deploy.test.sh
mutate deploy_pushes_x86_images scripts/deploy/deploy.sh 'if [ "$arch" != arm64 ]; then' 'if false; then' scripts/deploy/tests/deploy.test.sh
mutate deploy_pushes_a_tag_already_in_ecr scripts/deploy/deploy.sh 'if aws ecr describe-images' 'if false && aws ecr describe-images' scripts/deploy/tests/deploy.test.sh

# --- Smoke check ------------------------------------------------------------------------------------------------------
mutate smoke_ignores_the_csp scripts/deploy/smoke.sh '&& [[ "$csp" == *frame-ancestors* ]]' '' scripts/deploy/tests/smoke.test.sh
mutate smoke_ignores_the_health_status scripts/deploy/smoke.sh "&& jq -e '.status == \"ok\"' \"\$work/body\" >/dev/null 2>&1 " '' scripts/deploy/tests/smoke.test.sh
mutate smoke_accepts_any_html scripts/deploy/smoke.sh "&& grep -q '<div id=\"root\"></div>' \"\$work/body\" " '' scripts/deploy/tests/smoke.test.sh
mutate smoke_does_not_retry scripts/deploy/smoke.sh 'attempts=${SMOKE_ATTEMPTS:-20}' 'attempts=1' scripts/deploy/tests/smoke.test.sh

# --- Destroy script ---------------------------------------------------------------------------------------------------
mutate destroy_without_confirmation scripts/deploy/destroy.sh 'if [ "$1" != "$expected" ]; then' 'if false; then' scripts/deploy/tests/destroy.test.sh
mutate destroy_case_insensitive scripts/deploy/destroy.sh 'if [ "$1" != "$expected" ]; then' 'if [ "${1,,}" != "$expected" ]; then' scripts/deploy/tests/destroy.test.sh

echo "caught $caught, missed $missed"
exit $((missed > 0))
