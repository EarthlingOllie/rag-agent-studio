# KMS module (ticket 09-03): customer-managed keys with yearly rotation.
# - credentials: wraps the per-record data keys of Provider Credentials (ADR-0006). Only the API task role
#   will be granted it (ticket 09-04), so it is kept apart from the data key the worker also needs.
# - data: encrypts data at rest in RDS, ElastiCache, the Documents bucket and the platform secrets.
locals {
  module_name = "kms"
  name        = "${var.name_prefix}-${local.module_name}"
  tags        = merge(var.tags, { Module = local.module_name, ManagedBy = "terraform" })

  keys = {
    credentials = "Envelope encryption of Provider Credentials (ADR-0006)"
    data        = "Data at rest: RDS, ElastiCache, Documents bucket and platform secrets"
  }
}

data "aws_caller_identity" "current" {}

data "aws_partition" "current" {}

# Key administration and use are delegated to IAM in this account, which is the AWS default key policy.
# Task roles get only the actions they need through their own IAM policies (ticket 09-04).
# In a key policy, Resource "*" means this key only.
locals {
  key_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "EnableIamPoliciesInThisAccount"
      Effect    = "Allow"
      Principal = { AWS = "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root" }
      Action    = "kms:*"
      Resource  = "*"
    }]
  })
}

resource "aws_kms_key" "this" {
  for_each = local.keys

  description             = "${local.name}-${each.key}: ${each.value}"
  key_usage               = "ENCRYPT_DECRYPT"
  enable_key_rotation     = true
  rotation_period_in_days = var.rotation_period_in_days
  deletion_window_in_days = var.deletion_window_in_days
  policy                  = local.key_policy

  tags = merge(local.tags, { Name = "${local.name}-${each.key}", Purpose = each.key })
}

resource "aws_kms_alias" "this" {
  for_each = local.keys

  name          = "alias/${local.name}-${each.key}"
  target_key_id = aws_kms_key.this[each.key].key_id
}
