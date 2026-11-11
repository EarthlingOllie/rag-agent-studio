# Database module (ticket 09-03): RDS Postgres 16, encrypted, private, with automated backups (ADR-0010).
# pgvector is enabled by a migration (CREATE EXTENSION vector); RDS Postgres 16 ships the extension.
locals {
  module_name = "database"
  name        = "${var.name_prefix}-${local.module_name}"
  tags        = merge(var.tags, { Module = local.module_name, ManagedBy = "terraform" })

  port = 5432
}

resource "aws_db_subnet_group" "this" {
  name        = local.name
  description = "Private subnets for ${local.name}"
  subnet_ids  = var.subnet_ids

  tags = merge(local.tags, { Name = local.name })
}

# No egress rules: Terraform drops the default allow-all egress, and Postgres never starts connections.
resource "aws_security_group" "this" {
  name        = local.name
  description = "Postgres: connections only from the listed client security groups"
  vpc_id      = var.vpc_id

  tags = merge(local.tags, { Name = local.name })
}

resource "aws_vpc_security_group_ingress_rule" "clients" {
  for_each = var.client_security_group_ids

  security_group_id            = aws_security_group.this.id
  description                  = "Postgres from ${each.key}"
  referenced_security_group_id = each.value
  ip_protocol                  = "tcp"
  from_port                    = local.port
  to_port                      = local.port

  tags = merge(local.tags, { Name = "${local.name}-from-${each.key}" })
}

# Clients must use TLS; everything else stays on the RDS defaults.
resource "aws_db_parameter_group" "this" {
  name        = local.name
  family      = "postgres16"
  description = "Postgres 16 defaults, with TLS required for every connection"

  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }

  tags = merge(local.tags, { Name = local.name })
}

# The master password is 244 random bits (two version-4 UUIDs from crypto/rand) written only through
# write-only arguments, to RDS and to Secrets Manager in the same apply, so it never appears in Terraform
# state, plans or variables. uuid() is used instead of the aws_secretsmanager_random_password ephemeral
# resource because `terraform test` mock providers cannot serve ephemeral resources. Bump password_version
# to set a new password on both.
locals {
  generated_password = replace("${uuid()}${uuid()}", "-", "")
}

resource "aws_secretsmanager_secret" "master_password" {
  #checkov:skip=CKV2_AWS_57:Rotating the password needs a rotation Lambda and app reconnects; out of scope for the short-lived demo (spec 09).
  name                    = "${local.name}/master-password"
  description             = "Master password of ${local.name}. Injected into ECS tasks (ticket 09-04)."
  kms_key_id              = var.kms_key_arn
  recovery_window_in_days = 0

  tags = merge(local.tags, { Name = "${local.name}-master-password" })
}

resource "aws_secretsmanager_secret_version" "master_password" {
  secret_id                = aws_secretsmanager_secret.master_password.id
  secret_string_wo         = local.generated_password
  secret_string_wo_version = var.password_version

  # A replaced instance gets a fresh password, so the secret must be rewritten in the same apply.
  lifecycle {
    replace_triggered_by = [aws_db_instance.this.id]
  }
}

resource "aws_db_instance" "this" {
  #checkov:skip=CKV_AWS_118:Enhanced monitoring adds a paid CloudWatch stream the throwaway demo does not need.
  #checkov:skip=CKV_AWS_129:Exporting Postgres logs to CloudWatch adds paid ingestion; the RDS console keeps recent logs.
  #checkov:skip=CKV_AWS_157:Single-AZ by default to keep the demo cheap (spec 09 cost defaults); multi_az turns it on.
  #checkov:skip=CKV_AWS_293:Deletion protection is off by default so the demo can be destroyed in one run (spec 09 story 27); deletion_protection turns it on.
  #checkov:skip=CKV_AWS_353:Performance Insights is not needed for the demo; it can be enabled later without replacement.
  identifier     = local.name
  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class

  db_name                             = var.database_name
  username                            = var.master_username
  password_wo                         = local.generated_password
  password_wo_version                 = var.password_version
  iam_database_authentication_enabled = true

  allocated_storage     = var.allocated_storage_gb
  max_allocated_storage = var.max_allocated_storage_gb
  storage_type          = "gp3"
  storage_encrypted     = true
  kms_key_id            = var.kms_key_arn

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.this.id]
  parameter_group_name   = aws_db_parameter_group.this.name
  port                   = local.port
  publicly_accessible    = false
  multi_az               = var.multi_az

  backup_retention_period    = var.backup_retention_days
  backup_window              = "02:00-03:00"
  maintenance_window         = "sun:03:30-sun:04:30"
  copy_tags_to_snapshot      = true
  auto_minor_version_upgrade = true
  deletion_protection        = var.deletion_protection
  skip_final_snapshot        = !var.final_snapshot
  final_snapshot_identifier  = var.final_snapshot ? "${local.name}-final" : null
  delete_automated_backups   = !var.final_snapshot

  tags = merge(local.tags, { Name = local.name })
}
