# Cache module (ticket 09-03): ElastiCache Redis, the Celery broker and rate-limit store (ADR-0010),
# with encryption in transit and at rest and Redis AUTH on.
locals {
  module_name = "cache"
  name        = "${var.name_prefix}-${local.module_name}"
  tags        = merge(var.tags, { Module = local.module_name, ManagedBy = "terraform" })

  port = 6379

  # 244 random bits (two version-4 UUIDs from crypto/rand), written only through write-only arguments, to
  # ElastiCache and to Secrets Manager in the same apply, so the token never appears in state, plans or
  # variables. See the database module for why this is not the aws_secretsmanager_random_password ephemeral.
  generated_auth_token = replace("${uuid()}${uuid()}", "-", "")
}

resource "aws_elasticache_subnet_group" "this" {
  name        = local.name
  description = "Private subnets for ${local.name}"
  subnet_ids  = var.subnet_ids

  tags = merge(local.tags, { Name = local.name })
}

# No egress rules: Terraform drops the default allow-all egress, and Redis never starts connections.
resource "aws_security_group" "this" {
  name        = local.name
  description = "Redis: connections only from the listed client security groups"
  vpc_id      = var.vpc_id

  tags = merge(local.tags, { Name = local.name })
}

resource "aws_vpc_security_group_ingress_rule" "clients" {
  for_each = var.client_security_group_ids

  security_group_id            = aws_security_group.this.id
  description                  = "Redis from ${each.key}"
  referenced_security_group_id = each.value
  ip_protocol                  = "tcp"
  from_port                    = local.port
  to_port                      = local.port

  tags = merge(local.tags, { Name = "${local.name}-from-${each.key}" })
}

resource "aws_secretsmanager_secret" "auth_token" {
  #checkov:skip=CKV2_AWS_57:Rotating the token needs a rotation Lambda and client reconnects; out of scope for the short-lived demo (spec 09).
  name                    = "${local.name}/auth-token"
  description             = "Redis AUTH token of ${local.name}. Injected into ECS tasks (ticket 09-04)."
  kms_key_id              = var.kms_key_arn
  recovery_window_in_days = 0

  tags = merge(local.tags, { Name = "${local.name}-auth-token" })
}

resource "aws_secretsmanager_secret_version" "auth_token" {
  secret_id                = aws_secretsmanager_secret.auth_token.id
  secret_string_wo         = local.generated_auth_token
  secret_string_wo_version = var.auth_token_version

  # A replaced replication group gets a fresh token, so the secret must be rewritten in the same apply.
  lifecycle {
    replace_triggered_by = [aws_elasticache_replication_group.this.id]
  }
}

resource "aws_elasticache_replication_group" "this" {
  #checkov:skip=CKV_AWS_31:False positive: transit encryption is required and AUTH is set through auth_token_wo, which this check does not read (the tests assert both).
  #checkov:skip=CKV2_AWS_50:A single node keeps the demo cheap (spec 09 cost defaults); replicas >= 1 turns on Multi-AZ automatic failover.
  replication_group_id = local.name
  description          = "Redis for ${local.name}: Celery broker and rate limits"
  engine               = "redis"
  engine_version       = var.engine_version
  node_type            = var.node_type
  port                 = local.port

  num_cache_clusters         = var.replicas + 1
  automatic_failover_enabled = var.replicas > 0
  multi_az_enabled           = var.replicas > 0

  subnet_group_name  = aws_elasticache_subnet_group.this.name
  security_group_ids = [aws_security_group.this.id]

  at_rest_encryption_enabled = "true"
  kms_key_id                 = var.kms_key_arn
  transit_encryption_enabled = true
  transit_encryption_mode    = "required"
  auth_token_wo              = local.generated_auth_token
  auth_token_wo_version      = var.auth_token_version
  auth_token_update_strategy = "ROTATE"

  snapshot_retention_limit   = var.snapshot_retention_days
  snapshot_window            = "02:00-03:00"
  maintenance_window         = "sun:03:30-sun:04:30"
  auto_minor_version_upgrade = "true"
  apply_immediately          = true

  tags = merge(local.tags, { Name = local.name })
}
