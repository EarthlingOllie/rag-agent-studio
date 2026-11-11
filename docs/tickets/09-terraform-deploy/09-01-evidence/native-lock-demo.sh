#!/usr/bin/env bash
# Evidence only: exercises infra/envs/demo's real S3 backend block against a local moto S3 (no AWS account).
set -uo pipefail
WT=$1; MOTO=http://127.0.0.1:5055; B=rag-agent-studio-tfstate-123456789012
export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_REGION=eu-west-2
work=$(mktemp -d); cp -r "$WT/infra" "$work/"; cd "$work/infra/envs/demo"; rm -rf .terraform
echo "\$ curl -X PUT $MOTO/$B   # create the state bucket in local moto S3"
curl -s -o /dev/null -w 'HTTP %{http_code}\n' -X PUT "$MOTO/$B" -H 'Content-Type: application/xml' --data '<CreateBucketConfiguration><LocationConstraint>eu-west-2</LocationConstraint></CreateBucketConfiguration>'
cfg=(-backend-config="bucket=$B" -backend-config="region=eu-west-2" -backend-config="endpoints={s3=\"$MOTO\"}"
     -backend-config="use_path_style=true" -backend-config="skip_credentials_validation=true"
     -backend-config="skip_requesting_account_id=true" -backend-config="skip_metadata_api_check=true")
echo; echo '$ terraform init -input=false -backend-config=bucket=... (backend.tf unchanged: key + use_lockfile = true)'
terraform init -input=false -no-color "${cfg[@]}" | grep -E 'backend|Successfully'; echo "exit=${PIPESTATUS[0]}"
echo; echo '$ terraform plan -input=false (takes and releases the native lock)'
terraform plan -input=false -no-color >/dev/null; echo "exit=$?"
echo; echo "\$ grep tflock moto.log   # S3 requests moto served for the lock object"
sed 's/\x1b\[[0-9;]*m//g' "$2" | grep -o '"[A-Z]* /'"$B"'/envs/demo/terraform.tfstate.tflock[^"]*" [0-9]*' | sed 's/^/  /'
echo; echo '$ put a foreign lock object, as a concurrent run would, then plan again'
curl -s -o /dev/null -w 'HTTP %{http_code}\n' -X PUT "$MOTO/$B/envs/demo/terraform.tfstate.tflock" --data '{"ID":"11111111-2222-3333-4444-555555555555","Operation":"OperationTypeApply","Who":"other@ci","Version":"1.13.4","Created":"2026-11-05T00:00:00Z","Path":"'"$B"'/envs/demo/terraform.tfstate"}'
terraform plan -input=false -no-color -lock-timeout=3s 2>&1 | grep -E 'Error|ID:|Who:|Operation:' | sed 's/^/  /'; echo "exit=${PIPESTATUS[0]}"
rm -rf "$work"
