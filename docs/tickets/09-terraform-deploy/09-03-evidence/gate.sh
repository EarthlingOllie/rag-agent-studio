#!/bin/bash
# Applies one single-line mutation at a time, runs `terraform test` in that module, and restores the file.
# Run from anywhere in the repo. Set TF_CLI_CONFIG_FILE first if the provider comes from a local mirror.
cd "$(git rev-parse --show-toplevel)/infra/modules"
mutate() { # module, label, sed expression
  local m=$1 label=$2 expr=$3
  cp $m/main.tf /tmp/main.tf.bak
  sed -i "$expr" $m/main.tf
  echo "### $m: $label"
  diff /tmp/main.tf.bak $m/main.tf | grep -E "^[<>]"
  terraform -chdir=$m test -no-color 2>&1 | grep -E '\.\.\. fail$|^Success|^Failure' | head -4
  echo "exit=${PIPESTATUS[0]}"
  cp /tmp/main.tf.bak $m/main.tf
  echo
}
mutate kms "rotation turned off" 's/enable_key_rotation     = true/enable_key_rotation     = false/'
mutate kms "key policy opened to every AWS principal" 's|Principal = { AWS = "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root" }|Principal = { AWS = "*" }|'
mutate database "storage encryption off" 's/storage_encrypted     = true/storage_encrypted     = false/'
mutate database "publicly accessible" 's/publicly_accessible    = false/publicly_accessible    = true/'
mutate database "backups off" 's/backup_retention_period    = var.backup_retention_days/backup_retention_period    = 0/'
mutate database "Postgres 15" 's/family      = "postgres16"/family      = "postgres15"/'
mutate database "TLS no longer forced" 's/value = "1"/value = "0"/'
mutate database "ingress from the whole VPC CIDR" 's/referenced_security_group_id = each.value/cidr_ipv4                    = "10.0.0.0\/16"/'
mutate cache "transit encryption preferred, not required" 's/transit_encryption_mode    = "required"/transit_encryption_mode    = "preferred"/'
mutate cache "at-rest encryption off" 's/at_rest_encryption_enabled = "true"/at_rest_encryption_enabled = "false"/'
mutate cache "auth token in state" 's/auth_token_wo              = local.generated_auth_token/auth_token                 = local.generated_auth_token/'
mutate cache "secret written with a different version" 's/secret_string_wo_version = var.auth_token_version/secret_string_wo_version = 1/'
mutate storage "public policies allowed" 's/block_public_policy     = true/block_public_policy     = false/'
mutate storage "Documents on S3-managed keys" 's/sse_algorithm     = "aws:kms"/sse_algorithm     = "AES256"/'
mutate storage "CORS open to any origin" 's/allowed_origins = \[var.documents_cors_allowed_origin\]/allowed_origins = ["*"]/'
mutate storage "CORS allows DELETE" 's/allowed_methods = \["GET", "PUT"\]/allowed_methods = ["GET", "PUT", "DELETE"]/'
mutate storage "OAC stops signing" 's/signing_behavior                  = "always"/signing_behavior                  = "never"/'
mutate storage "static reads not tied to the distribution" 's/Condition = { StringEquals = { "AWS:SourceArn" = var.static_assets_distribution_arn } }/Condition = {}/'
mutate storage "TLS deny dropped" 's/"aws:SecureTransport" = "false"/"aws:SecureTransport" = "true"/'
for m in kms database cache storage; do terraform -chdir=$m test -no-color 2>&1 | tail -1 | sed "s|^|after restore, $m: |"; done
echo "### checkov: the justified skips are load-bearing (each removed in turn)"
for pair in "cache:CKV2_AWS_50" "database:CKV_AWS_293" "storage:CKV_AWS_145"; do
  m=${pair%%:*}; id=${pair#*:}
  cp $m/main.tf /tmp/main.tf.bak
  sed -i "/#checkov:skip=$id:/d" $m/main.tf
  echo "\$ checkov -d $m (without the $id skip)"
  checkov -d $m --framework terraform --compact --quiet --skip-download 2>&1 | grep -E "^Passed|^Check:"
  echo "exit=${PIPESTATUS[0]}"
  cp /tmp/main.tf.bak $m/main.tf
done
