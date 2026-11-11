# Seed in AWS (ticket 10-05): `python -m app.seed`, the command behind `make seed`, as a one-off Fargate task on the
# backend image. The seed workflow (scripts/deploy/seed.sh) runs it after a deploy, waits for it and prints its log,
# which holds the demo sign-in details; `--reset` is a command override. The seed runs the API in process and goes
# through its own services, so it needs what the API needs to create the demo data: Postgres, Redis (ingestion is
# queued for the worker), the documents bucket and the credentials key. It has its own roles, log group and security
# group, and unlike the API it may not assume customer Bedrock roles. The demo Documents are in the image, at /seed.

locals {
  seed_environment = merge(local.base_environment, local.app_environment)
  seed_secrets     = local.secrets["api"]

  # The API's statements, minus the Bedrock one.
  seed_task_role_policy = {
    Version = "2012-10-17"
    Statement = concat(local.documents_statements, [
      {
        Sid      = "ProviderCredentialEnvelopes"
        Effect   = "Allow"
        Action   = ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey"]
        Resource = var.credentials_key_arn
      },
    ])
  }

  seed_execution_role_policy = {
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
        Resource = "${aws_cloudwatch_log_group.seed.arn}:log-stream:*"
      },
      {
        Sid      = "ReadOwnSecrets"
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = values(local.seed_secrets)
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

resource "aws_cloudwatch_log_group" "seed" {
  #checkov:skip=CKV_AWS_158:Encrypted at rest by CloudWatch's own key, as the services' log groups; container logs are scrubbed of secrets (ticket 01-03).
  #checkov:skip=CKV_AWS_338:A year of retention is not needed for a throwaway demo; log_retention_days sets it.
  name              = "/ecs/${local.name}/seed"
  retention_in_days = var.log_retention_days

  tags = merge(local.tags, { Name = "${local.name}-seed" })
}

resource "aws_iam_role" "seed_task" {
  name               = "${local.name}-seed-task"
  description        = "Task role of the seed task: the documents bucket and the credentials key, as the API"
  assume_role_policy = jsonencode(local.task_trust_policy)

  tags = merge(local.tags, { Name = "${local.name}-seed-task" })
}

resource "aws_iam_role_policy" "seed_task" {
  name   = "${local.name}-seed-task"
  role   = aws_iam_role.seed_task.id
  policy = jsonencode(local.seed_task_role_policy)
}

resource "aws_iam_role" "seed_execution" {
  name               = "${local.name}-seed-execution"
  description        = "Execution role of the seed task: pulls the image, writes logs, reads the seed's secrets"
  assume_role_policy = jsonencode(local.task_trust_policy)

  tags = merge(local.tags, { Name = "${local.name}-seed-execution" })
}

resource "aws_iam_role_policy" "seed_execution" {
  name   = "${local.name}-seed-execution"
  role   = aws_iam_role.seed_execution.id
  policy = jsonencode(local.seed_execution_role_policy)
}

resource "aws_security_group" "seed" {
  #checkov:skip=CKV2_AWS_5:False positive: the seed workflow attaches it to each seed task through run-task's network configuration (the seed_task output).
  name        = "${local.name}-seed"
  description = "seed tasks"
  vpc_id      = var.vpc_id

  tags = merge(local.tags, { Name = "${local.name}-seed" })
}

# HTTPS for image pulls, logs, secrets, S3 and KMS (through the VPC endpoints); Postgres and Redis for the in-process API.
resource "aws_vpc_security_group_egress_rule" "seed" {
  for_each = {
    https    = { port = 443, cidr = "0.0.0.0/0", security_group = null }
    postgres = { port = var.database.port, cidr = null, security_group = var.database.security_group_id }
    redis    = { port = var.cache.port, cidr = null, security_group = var.cache.security_group_id }
  }

  security_group_id            = aws_security_group.seed.id
  description                  = "seed to ${each.key}"
  ip_protocol                  = "tcp"
  from_port                    = each.value.port
  to_port                      = each.value.port
  cidr_ipv4                    = each.value.cidr
  referenced_security_group_id = each.value.security_group

  tags = merge(local.tags, { Name = "${local.name}-seed-${each.key}" })
}

resource "aws_ecs_task_definition" "seed" {
  family                   = "${local.name}-seed"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.seed_task_size.cpu)
  memory                   = tostring(var.seed_task_size.memory)
  task_role_arn            = aws_iam_role.seed_task.arn
  execution_role_arn       = aws_iam_role.seed_execution.arn

  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([{
    name                   = "seed"
    image                  = local.image
    command                = ["python", "-m", "app.seed"]
    essential              = true
    environment            = [for name, value in local.seed_environment : { name = name, value = value }]
    secrets                = [for name, arn in local.seed_secrets : { name = name, valueFrom = arn }]
    readonlyRootFilesystem = true
    mountPoints            = [{ sourceVolume = "tmp", containerPath = "/tmp", readOnly = false }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.seed.name
        "awslogs-region"        = local.region
        "awslogs-stream-prefix" = "seed"
      }
    }
  }])

  volume {
    name = "tmp"
  }

  tags = merge(local.tags, { Name = "${local.name}-seed" })
}
