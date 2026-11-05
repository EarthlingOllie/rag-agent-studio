#!/bin/bash
# Applies one single-line security regression at a time to the ecr or ecs module, runs `terraform test` in that
# module, and restores the file. Every regression must fail the tests (exit 1). Then removes needed Checkov skips
# one at a time and shows Checkov failing. Set TF_CLI_CONFIG_FILE first if the provider comes from a local mirror.
cd "$(git rev-parse --show-toplevel)/infra/modules"
BAK=$(mktemp)
mutate() { # module, label, sed expression
  local m=$1 label=$2 expr=$3
  cp $m/main.tf "$BAK"
  sed -i "$expr" $m/main.tf
  echo "### $m: $label"
  diff "$BAK" $m/main.tf | grep -E "^[<>]" || echo "!! sed did not change the file"
  terraform -chdir=$m test -no-color 2>&1 | grep -E '\.\.\. fail$|^Success|^Failure' | head -4
  echo "exit=${PIPESTATUS[0]}"
  cp "$BAK" $m/main.tf
  echo
}
mutate ecr "scan on push off" 's/scan_on_push = true/scan_on_push = false/'
mutate ecr "mutable tags" 's/image_tag_mutability = "IMMUTABLE"/image_tag_mutability = "MUTABLE"/'
mutate ecr "untagged images kept forever (lifecycle rule 1 dropped to 3650 days)" 's/countNumber = var.untagged_expiry_days/countNumber = 3650/'
mutate ecr "images on AWS-managed encryption" 's/encryption_type = "KMS"/encryption_type = "AES256"/'
mutate ecs "x86 tasks" 's/cpu_architecture        = "ARM64"/cpu_architecture        = "X86_64"/'
mutate ecs "task size ignores the variable" 's/memory                   = tostring(var.task_sizes\[each.key\].memory)/memory                   = "8192"/'
mutate ecs "assume-role without an external ID" 's/Null            = { "sts:ExternalId" = "false" }/Null            = { "sts:ExternalId" = "true" }/'
mutate ecs "assume-role in this account allowed" '/StringNotEquals = { "aws:ResourceAccount" = local.account_id }/d'
mutate ecs "worker given the credentials key" 's/Statement = local.documents_statements/Statement = concat(local.documents_statements, [{ Sid = "X", Effect = "Allow", Action = "kms:Decrypt", Resource = var.credentials_key_arn }])/'
mutate ecs "Documents wildcard actions" 's/Action   = \["s3:GetObject", "s3:PutObject", "s3:DeleteObject"\]/Action   = "s3:*"/'
mutate ecs "task trust without the source-account condition" 's/StringEquals = { "aws:SourceAccount" = local.account_id }/StringEquals = {}/'
mutate ecs "ALB open to the internet" 's/prefix_list_id    = data.aws_ec2_managed_prefix_list.cloudfront.id/cidr_ipv4         = "0.0.0.0\/0"/'
mutate ecs "listener forwards without the header" 's/type = "fixed-response"/type = "forward"/'
mutate ecs "header rule matches any value" 's/values           = \[terraform_data.origin_secret.output\]/values           = ["*"]/'
mutate ecs "API tasks get public IPs" 's/assign_public_ip = false/assign_public_ip = true/'
mutate ecs "session secret written into state" 's/secret_string_wo         = replace/secret_string            = replace/'
mutate ecs "Beat given the database password" 's/^    beat = merge({$/    beat = merge({ DATABASE_PASSWORD = var.database.password_secret_arn,/'
mutate ecs "execution role may read every secret" 's/Resource = values(local.secrets\[k\])/Resource = "*"/'
mutate ecs "KMS decrypt outside Secrets Manager" 's/Condition = { StringEquals = { "kms:ViaService" = "secretsmanager.${local.region}.amazonaws.com" } }/Condition = {}/'
mutate ecs "logs kept forever" 's/retention_in_days = var.log_retention_days/retention_in_days = 0/'
mutate ecs "writable root filesystem" 's/readonlyRootFilesystem = true/readonlyRootFilesystem = false/'
mutate ecs "Beat rolls with two schedulers" 's/deployment_maximum_percent         = each.key == "beat" ? 100 : 200/deployment_maximum_percent         = 200/'
mutate ecs "egress to Postgres from Beat" 's/for k in \["api", "worker"\] : "${k}-postgres"/for k in local.services : "${k}-postgres"/'

skip() { # module, check id
  local m=$1 id=$2
  cp $m/main.tf "$BAK"
  sed -i "/#checkov:skip=$id:/d" $m/main.tf
  echo "### $m: without the $id skip"
  (cd .. && checkov --config-file .checkov.yaml --check "$id" 2>&1 | grep -E "^(Passed|Check:)|FAILED" | head -4)
  cp "$BAK" $m/main.tf
  echo
}
skip ecs CKV2_AWS_20
skip ecs CKV_AWS_2
skip ecs CKV_AWS_260
rm -f "$BAK"
