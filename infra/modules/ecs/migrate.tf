# Migrations (ticket 09-06): `alembic upgrade head` as a one-off Fargate task on the backend image. The deploy
# workflow (scripts/deploy/deploy.sh) runs it at the new tag and waits for it to exit 0 before rolling the services,
# so the schema is always ready for the new code (spec 09 story 26). It has its own least-privilege roles, log group
# and security group: it reaches only Postgres and HTTPS, and its task role has no AWS permissions at all.

locals {
  # The settings need a Redis address and the local key too, though migrations use neither: no AUTH token is given
  # and the security group has no route to Redis.
  migrate_environment = local.base_environment
  migrate_secrets     = merge({ DATABASE_PASSWORD = var.database.password_secret_arn }, local.key_wrapper_secret, local.logfire_secret)

  migration_execution_role_policy = {
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "AuthenticateToEcr"
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*" # GetAuthorizationToken has no resource-level permissions.
      },
      {
        Sid      = "PullTheBackendImage"
        Effect   = "Allow"
        Action   = ["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"]
        Resource = var.image_repository_arn
      },
      {
        Sid      = "WriteOwnLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.migrate.arn}:log-stream:*"
      },
      {
        Sid      = "ReadOwnSecrets"
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = values(local.migrate_secrets)
      },
      {
        Sid       = "DecryptSecretsThroughSecretsManager"
        Effect    = "Allow"
        Action    = "kms:Decrypt"
        Resource  = var.data_key_arn
        Condition = { StringEquals = { "kms:ViaService" = "secretsmanager.${local.region}.amazonaws.com" } }
      },
    ]
  }
}

resource "aws_cloudwatch_log_group" "migrate" {
  #checkov:skip=CKV_AWS_158:Encrypted at rest by CloudWatch's own key, as the services' log groups; container logs are scrubbed of secrets (ticket 01-03).
  #checkov:skip=CKV_AWS_338:A year of retention is not needed for a throwaway demo; log_retention_days sets it.
  name              = "/ecs/${local.name}/migrate"
  retention_in_days = var.log_retention_days

  tags = merge(local.tags, { Name = "${local.name}-migrate" })
}

# No aws_iam_role_policy: migrations only talk to Postgres.
resource "aws_iam_role" "migrate_task" {
  name               = "${local.name}-migrate-task"
  description        = "Task role of the migration task: no AWS permissions"
  assume_role_policy = jsonencode(local.task_trust_policy)

  tags = merge(local.tags, { Name = "${local.name}-migrate-task" })
}

resource "aws_iam_role" "migrate_execution" {
  name               = "${local.name}-migrate-execution"
  description        = "Execution role of the migration task: pulls the image, writes logs, reads the database password"
  assume_role_policy = jsonencode(local.task_trust_policy)

  tags = merge(local.tags, { Name = "${local.name}-migrate-execution" })
}

resource "aws_iam_role_policy" "migrate_execution" {
  name   = "${local.name}-migrate-execution"
  role   = aws_iam_role.migrate_execution.id
  policy = jsonencode(local.migration_execution_role_policy)
}

resource "aws_security_group" "migrate" {
  #checkov:skip=CKV2_AWS_5:False positive: the deploy workflow attaches it to each migration task through run-task's network configuration (the migration_task output).
  name        = "${local.name}-migrate"
  description = "migration tasks"
  vpc_id      = var.vpc_id

  tags = merge(local.tags, { Name = "${local.name}-migrate" })
}

# HTTPS for image pulls, logs and the secret (through the VPC endpoints); Postgres for the migrations themselves.
resource "aws_vpc_security_group_egress_rule" "migrate" {
  for_each = {
    https    = { port = 443, cidr = "0.0.0.0/0", security_group = null }
    postgres = { port = var.database.port, cidr = null, security_group = var.database.security_group_id }
  }

  security_group_id            = aws_security_group.migrate.id
  description                  = "migrate to ${each.key}"
  ip_protocol                  = "tcp"
  from_port                    = each.value.port
  to_port                      = each.value.port
  cidr_ipv4                    = each.value.cidr
  referenced_security_group_id = each.value.security_group

  tags = merge(local.tags, { Name = "${local.name}-migrate-${each.key}" })
}

resource "aws_ecs_task_definition" "migrate" {
  family                   = "${local.name}-migrate"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.migration_task_size.cpu)
  memory                   = tostring(var.migration_task_size.memory)
  task_role_arn            = aws_iam_role.migrate_task.arn
  execution_role_arn       = aws_iam_role.migrate_execution.arn

  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([{
    name                   = "migrate"
    image                  = local.image
    command                = ["alembic", "upgrade", "head"]
    essential              = true
    environment            = [for name, value in local.migrate_environment : { name = name, value = value }]
    secrets                = [for name, arn in local.migrate_secrets : { name = name, valueFrom = arn }]
    readonlyRootFilesystem = true
    mountPoints            = [{ sourceVolume = "tmp", containerPath = "/tmp", readOnly = false }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.migrate.name
        "awslogs-region"        = local.region
        "awslogs-stream-prefix" = "migrate"
      }
    }
  }])

  volume {
    name = "tmp"
  }

  tags = merge(local.tags, { Name = "${local.name}-migrate" })
}
