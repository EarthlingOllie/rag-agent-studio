# Compute module (ticket 09-04): the API, the two worker pools and Beat as ECS Fargate services on ARM64 (ADR-0010).
# All four run the one backend image with different commands. The ALB in front of the API accepts only
# CloudFront, carrying the secret origin header (ADR-0011). Ticket 22-04 split the worker into a general pool on
# Fargate Spot and a runs pool on regular Fargate, each serving its own queue (ADR-0021).
locals {
  module_name = "ecs"
  name        = "${var.name_prefix}-${local.module_name}"
  tags        = merge(var.tags, { Module = local.module_name, ManagedBy = "terraform" })

  api_port = 8000
  image    = "${var.image_repository_url}:${var.image_tag}"

  # The same commands as docker-compose.yml, minus the API's `alembic upgrade head`: in AWS, migrations run as
  # a one-off task before services roll (spec 09, ticket 09-06). Locally one worker serves both queues; here each
  # pool serves only its own (spec 22 story 39), running as many jobs at once as the slots its pool scales by.
  worker_command = ["celery", "-A", "app.worker.main", "--quiet", "worker", "--loglevel=INFO"]
  commands = {
    api              = ["python", "-m", "app.serve"]
    "worker-general" = concat(local.worker_command, ["--concurrency=${var.scaling["worker-general"].jobs_per_task}", "--queues=${var.queues.general.name}"])
    "worker-runs"    = concat(local.worker_command, ["--concurrency=${var.scaling["worker-runs"].jobs_per_task}", "--queues=${var.queues.runs.name}"])
    beat             = ["celery", "-A", "app.worker.main", "--quiet", "beat", "--loglevel=INFO", "--schedule=/tmp/celerybeat-schedule"]
  }
  services = toset(keys(local.commands))
  workers  = toset(["worker-general", "worker-runs"])

  # Where each service's tasks run: the general pool's jobs restart for free, so it takes Fargate Spot unless
  # worker_spot is off; the runs pool's jobs are long and paid for, so it stays on regular Fargate (ADR-0021).
  capacity_providers = { for k in local.services : k => k == "worker-general" && var.worker_spot ? "FARGATE_SPOT" : "FARGATE" }

  # A worker is given two minutes, Fargate's most, between SIGTERM and SIGKILL: a Spot warning is two minutes, and a
  # short job finishes inside it (spec 22 story 17). The API and Beat keep the default.
  stop_timeouts = { for k in local.workers : k => { stopTimeout = 120 } }

  # Account and region come from the given ARNs, so the policies are fully known at plan time.
  account_id = split(":", var.data_key_arn)[4]
  region     = data.aws_region.current.region
}

data "aws_region" "current" {}

# --- Task roles: what each service's code may call ----------------------------------------------------------------

locals {
  task_trust_policy = {
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "aws:SourceAccount" = local.account_id }
        ArnLike      = { "aws:SourceArn" = "arn:aws:ecs:${local.region}:${local.account_id}:*" }
      }
    }]
  }

  # Documents: the API uploads, serves and deletes them; the general pool reads them for ingestion and purges them.
  documents_statements = [
    {
      Sid      = "DocumentObjects"
      Effect   = "Allow"
      Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
      Resource = "${var.documents_bucket_arn}/*"
    },
    {
      Sid      = "DocumentsBucket"
      Effect   = "Allow"
      Action   = ["s3:ListBucket"]
      Resource = var.documents_bucket_arn
    },
    {
      Sid      = "DocumentsEncryption"
      Effect   = "Allow"
      Action   = ["kms:Decrypt", "kms:GenerateDataKey"]
      Resource = var.data_key_arn
    },
  ]

  # Jobs go through the queue module's queues (ADR-0021). Sending needs no KMS permission: the queues use SSE-SQS.
  queue_arns = [var.queues.general.arn, var.queues.runs.arn]
  send_to_both_queues = {
    Sid      = "SendJobsToBothQueues"
    Effect   = "Allow"
    Action   = ["sqs:SendMessage"]
    Resource = local.queue_arns
  }

  # Ingestion embeds with the Project's provider Embedding Model (ticket 03-09), and Runs call the Agent's model, so
  # both pools open credential envelopes. They only decrypt: sealing secrets stays with the API.
  open_credential_envelopes = {
    Sid      = "OpenProviderCredentialEnvelopes"
    Effect   = "Allow"
    Action   = ["kms:Decrypt"]
    Resource = var.credentials_key_arn
  }

  # Each pool receives only from its own queue, so it can't take the other pool's jobs (spec 22 story 34).
  receive_own_queue = { for pool, queue in { "worker-general" = var.queues.general, "worker-runs" = var.queues.runs } : pool => {
    Sid      = "ReceiveJobsFromItsOwnQueue"
    Effect   = "Allow"
    Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility", "sqs:GetQueueAttributes"]
    Resource = queue.arn
  } }

  # A worker protects its task from scale-in while it holds a job (ticket 22-06), through the ECS agent's endpoint,
  # which acts on the calling task alone. IAM narrows it to this cluster's tasks carrying the pool's own Name tag
  # (services propagate their tags to their tasks), so one pool can't unprotect the other's tasks.
  protect_own_task = { for pool in local.workers : pool => {
    Sid       = "ProtectItsOwnTaskFromScaleIn"
    Effect    = "Allow"
    Action    = ["ecs:GetTaskProtection", "ecs:UpdateTaskProtection"]
    Resource  = "arn:aws:ecs:${local.region}:${local.account_id}:task/${local.name}/*"
    Condition = { StringEquals = { "aws:ResourceTag/Name" = "${local.name}-${pool}" } }
  } }

  # Each service's policy, or null for none.
  task_role_policies = {
    api = {
      Version = "2012-10-17"
      Statement = concat(local.documents_statements, [
        {
          Sid      = "ProviderCredentialEnvelopes"
          Effect   = "Allow"
          Action   = ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey"]
          Resource = var.credentials_key_arn
        },
        {
          # Customer Bedrock roles live in other accounts and must be assumed with the Organisation's external ID
          # (spec 09 story 13). The customer's trust policy pins the value; this side refuses calls without one.
          Sid      = "AssumeCustomerBedrockRolesWithExternalId"
          Effect   = "Allow"
          Action   = "sts:AssumeRole"
          Resource = "arn:aws:iam::*:role/*"
          Condition = {
            Null            = { "sts:ExternalId" = "false" }
            StringNotEquals = { "aws:ResourceAccount" = local.account_id }
          }
        },
        local.send_to_both_queues,
      ])
    }
    # The general pool ingests, re-embeds and deletes Documents, so it keeps the Documents statements. A job may
    # queue follow-on work on either queue.
    "worker-general" = {
      Version = "2012-10-17"
      Statement = concat(local.documents_statements, [
        local.open_credential_envelopes,
        local.receive_own_queue["worker-general"],
        local.send_to_both_queues,
        local.protect_own_task["worker-general"],
      ])
    }
    # Evaluation Runs and Suggestion runs read the database and call models; they never touch Documents' objects.
    "worker-runs" = {
      Version = "2012-10-17"
      Statement = [
        local.open_credential_envelopes,
        local.receive_own_queue["worker-runs"],
        local.send_to_both_queues,
        local.protect_own_task["worker-runs"],
      ]
    }
    # Beat only queues the scheduled jobs, which all go to the general queue: its one AWS permission.
    beat = {
      Version = "2012-10-17"
      Statement = [{
        Sid      = "SendJobsToTheGeneralQueue"
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = var.queues.general.arn
      }]
    }
  }
}

resource "aws_iam_role" "task" {
  for_each = local.services

  name               = "${local.name}-${each.key}-task"
  description        = "Task role of the ${each.key} service: what its code may call"
  assume_role_policy = jsonencode(local.task_trust_policy)

  tags = merge(local.tags, { Name = "${local.name}-${each.key}-task" })
}

resource "aws_iam_role_policy" "task" {
  for_each = { for k, p in local.task_role_policies : k => p if p != null }

  name   = "${local.name}-${each.key}-task"
  role   = aws_iam_role.task[each.key].id
  policy = jsonencode(each.value)
}

resource "aws_ecs_cluster" "this" {
  #checkov:skip=CKV_AWS_65:Container Insights adds paid custom metrics the throwaway demo does not need; service metrics and logs remain.
  name = local.name

  tags = merge(local.tags, { Name = local.name })
}

# Fargate for the API, Beat and the runs pool; Fargate Spot for the general pool unless worker_spot is off. ECS does
# not fall back from Spot to regular capacity by itself (spec 22 risks).
resource "aws_ecs_cluster_capacity_providers" "this" {
  cluster_name       = aws_ecs_cluster.this.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
    base              = 0
  }
}

# --- Configuration: plain settings as environment variables, secrets by reference to Secrets Manager ---------------

locals {
  documents_bucket = split(":::", var.documents_bucket_arn)[1]

  # Names match backend/app/core/settings.py. The settings build DATABASE_URL and REDIS_URL from the parts, adding
  # the password and AUTH token ECS injects from Secrets Manager. Every process loads the same settings, so Beat
  # and the migration task are given the parts they never connect to as well (but not the credentials).
  # infra/modules/ecs/tests/task-settings.json records the result; the backend test suite loads it into Settings.
  common_environment = {
    ENVIRONMENT = var.tags["Environment"]
    AWS_REGION  = local.region
  }
  database_environment = {
    DATABASE_HOST = var.database.address
    DATABASE_PORT = tostring(var.database.port)
    DATABASE_NAME = var.database.name
    DATABASE_USER = var.database.username
    DATABASE_TLS  = tostring(var.database.tls) # On AWS the parameter group sets rds.force_ssl.
  }
  cache_environment = {
    REDIS_HOST = var.cache.address
    REDIS_PORT = tostring(var.cache.port)
    REDIS_TLS  = "true"
  }
  # Named by Terraform, so no task needs permission to list or create queues (spec 22 story 8).
  queue_environment = {
    GENERAL_QUEUE_NAME = var.queues.general.name
    GENERAL_QUEUE_URL  = var.queues.general.url
    RUNS_QUEUE_NAME    = var.queues.runs.name
    RUNS_QUEUE_URL     = var.queues.runs.url
  }
  # What the API and the worker pools need beyond the data stores: Documents in S3, credential envelopes sealed by KMS, the
  # Studio's public address for links in emails, and the platform's public base URL, where ElevenLabs reaches the
  # turn endpoint for Calls (spec 20). CloudFront serves the API on the Studio's address, so they are the same.
  app_environment = {
    OBJECT_STORE        = "s3"
    OBJECT_STORE_BUCKET = local.documents_bucket
    OBJECT_STORE_REGION = local.region
    KEY_WRAPPER         = "kms"
    KMS_KEY_ID          = var.credentials_key_arn
    STUDIO_URL          = var.studio_url
    PUBLIC_BASE_URL     = var.studio_url
  }
  # The proxies whose X-Forwarded-For entries the API believes when finding a Visitor's IP for per-IP rate limits
  # (spec 06; backend/app/core/client_ip.py): the ALB, which connects from inside the VPC, and CloudFront's
  # origin-facing servers, the only addresses the ALB admits. CloudFront appends the viewer's address and the ALB
  # appends CloudFront's, so the first untrusted address from the right is the Visitor's.
  trusted_proxies = join(",", concat([var.vpc_cidr], sort([for e in data.aws_ec2_managed_prefix_list.cloudfront.entries : e.cidr])))

  base_environment = merge(local.common_environment, local.database_environment, local.cache_environment, local.queue_environment)
  environment = {
    # The API's task role is the principal Organisations trust in their Bedrock roles (spec 09 story 13).
    # The demo pages' routes (ticket 10-03) are the API's alone, and only in a demo environment.
    api = merge(local.base_environment, local.app_environment, {
      BEDROCK_PLATFORM_PRINCIPAL = aws_iam_role.task["api"].arn
      TRUSTED_PROXIES            = local.trusted_proxies
    }, var.demo_pages ? { DEMO_PAGES = "true" } : {})
    "worker-general" = merge(local.base_environment, local.app_environment)
    "worker-runs"    = merge(local.base_environment, local.app_environment)
    beat             = local.base_environment
  }

  # What each container (the services, the migration and the seed task) is given: the module's settings plus the
  # environment's extra_environment (ticket 23-02), which may add settings but never replace one of the module's.
  module_environment = merge(local.environment, { migrate = local.migrate_environment, seed = local.seed_environment })
  # The API also gets api_extra_environment (ticket 23-04).
  container_environment = {
    for k, e in local.module_environment : k => merge(e, var.extra_environment, k == "api" ? var.api_extra_environment : {})
  }
  extra_environment_overrides = sort(setunion(
    setintersection(toset(keys(var.extra_environment)), toset(flatten([for e in values(local.module_environment) : keys(e)]))),
    setintersection(toset(keys(var.api_extra_environment)), toset(keys(local.module_environment.api))),
  ))

  # Each service gets only the secrets it uses. ECS reads them at task start with the execution role.
  # LOCAL_KEY_WRAPPER_KEY signs widget tokens; every process's settings require it.
  logfire_secret     = var.logfire_token_secret_arn == null ? {} : { LOGFIRE_TOKEN = var.logfire_token_secret_arn }
  key_wrapper_secret = { LOCAL_KEY_WRAPPER_KEY = aws_secretsmanager_secret.platform["key-wrapper"].arn }
  worker_secrets = merge({
    DATABASE_PASSWORD = var.database.password_secret_arn
    REDIS_AUTH_TOKEN  = var.cache.auth_token_secret_arn
  }, local.key_wrapper_secret, local.logfire_secret)
  secrets = {
    api = merge({
      DATABASE_PASSWORD = var.database.password_secret_arn
      REDIS_AUTH_TOKEN  = var.cache.auth_token_secret_arn
      SESSION_SECRET    = aws_secretsmanager_secret.platform["session"].arn
    }, local.key_wrapper_secret, local.logfire_secret)
    "worker-general" = local.worker_secrets
    "worker-runs"    = local.worker_secrets
    beat = merge({
      REDIS_AUTH_TOKEN = var.cache.auth_token_secret_arn
    }, local.key_wrapper_secret, local.logfire_secret)
  }
}

resource "aws_cloudwatch_log_group" "service" {
  #checkov:skip=CKV_AWS_158:Encrypted at rest by CloudWatch's own key. A KMS key would need a CloudWatch Logs grant in the data key's policy; container logs are scrubbed of secrets (ticket 01-03).
  #checkov:skip=CKV_AWS_338:A year of retention is not needed for a throwaway demo; log_retention_days sets it.
  for_each = local.services

  name              = "/ecs/${local.name}/${each.key}"
  retention_in_days = var.log_retention_days

  tags = merge(local.tags, { Name = "${local.name}-${each.key}" })
}

# --- Execution roles: what ECS itself needs to start each service's tasks ------------------------------------------

locals {
  execution_role_policies = { for k in local.services : k => {
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
        Resource = "${aws_cloudwatch_log_group.service[k].arn}:log-stream:*"
      },
      {
        Sid      = "ReadOwnSecrets"
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = values(local.secrets[k])
      },
      {
        Sid       = "DecryptSecretsThroughSecretsManager"
        Effect    = "Allow"
        Action    = "kms:Decrypt"
        Resource  = var.data_key_arn
        Condition = { StringEquals = { "kms:ViaService" = "secretsmanager.${local.region}.amazonaws.com" } }
      },
    ]
  } }
}

resource "aws_iam_role" "execution" {
  for_each = local.services

  name               = "${local.name}-${each.key}-execution"
  description        = "Execution role of the ${each.key} service: pulls the image, writes logs, reads its secrets"
  assume_role_policy = jsonencode(local.task_trust_policy)

  tags = merge(local.tags, { Name = "${local.name}-${each.key}-execution" })
}

resource "aws_iam_role_policy" "execution" {
  for_each = local.services

  name   = "${local.name}-${each.key}-execution"
  role   = aws_iam_role.execution[each.key].id
  policy = jsonencode(local.execution_role_policies[each.key])
}

resource "aws_ecs_task_definition" "this" {
  for_each = local.services

  family                   = "${local.name}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.task_sizes[each.key].cpu)
  memory                   = tostring(var.task_sizes[each.key].memory)
  task_role_arn            = aws_iam_role.task[each.key].arn
  execution_role_arn       = aws_iam_role.execution[each.key].arn

  runtime_platform {
    cpu_architecture        = var.cpu_architecture
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([merge({
    name                   = each.key
    image                  = local.image
    command                = local.commands[each.key]
    essential              = true
    portMappings           = each.key == "api" ? [{ containerPort = local.api_port, protocol = "tcp" }] : []
    environment            = [for name, value in local.container_environment[each.key] : { name = name, value = value }]
    secrets                = [for name, arn in local.secrets[each.key] : { name = name, valueFrom = arn }]
    readonlyRootFilesystem = true
    mountPoints            = [{ sourceVolume = "tmp", containerPath = "/tmp", readOnly = false }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.service[each.key].name
        "awslogs-region"        = local.region
        "awslogs-stream-prefix" = each.key
      }
    }
  }, lookup(local.stop_timeouts, each.key, {}))])

  # Task-local scratch space for /tmp: the root filesystem is read-only.
  volume {
    name = "tmp"
  }

  tags = merge(local.tags, { Name = "${local.name}-${each.key}" })

  lifecycle {
    precondition {
      condition     = length(local.extra_environment_overrides) == 0
      error_message = "extra_environment and api_extra_environment may only add settings; they must not replace the module's own: ${join(", ", local.extra_environment_overrides)}."
    }
  }
}

# --- Edge: an ALB only CloudFront can reach, forwarding only requests with the secret header (ADR-0011) -----------

data "aws_ec2_managed_prefix_list" "cloudfront" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

# 256 random bits (two version-4 UUIDs from crypto/rand), generated once and kept until origin_secret_version
# changes. Unlike the database password it must live in state: both the listener rule and CloudFront's
# custom origin header (ticket 09-05) are configured with the value itself.
resource "terraform_data" "origin_secret" {
  input            = replace("${uuid()}${uuid()}", "-", "")
  triggers_replace = var.origin_secret_version

  lifecycle {
    ignore_changes = [input]
  }
}

resource "aws_security_group" "alb" {
  name        = "${local.name}-alb"
  description = "ALB: HTTP from CloudFront's origin-facing prefix list only"
  vpc_id      = var.vpc_id

  tags = merge(local.tags, { Name = "${local.name}-alb" })
}

resource "aws_vpc_security_group_ingress_rule" "alb" {
  #checkov:skip=CKV_AWS_260:False positive: the source is CloudFront's origin-facing prefix list, not 0.0.0.0/0 (asserted in tests).
  security_group_id = aws_security_group.alb.id
  description       = "HTTP from CloudFront origin-facing servers"
  prefix_list_id    = data.aws_ec2_managed_prefix_list.cloudfront.id
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80

  tags = merge(local.tags, { Name = "${local.name}-alb-from-cloudfront" })
}

resource "aws_vpc_security_group_egress_rule" "alb_to_api" {
  security_group_id            = aws_security_group.alb.id
  description                  = "To the API tasks"
  referenced_security_group_id = aws_security_group.service["api"].id
  ip_protocol                  = "tcp"
  from_port                    = local.api_port
  to_port                      = local.api_port

  tags = merge(local.tags, { Name = "${local.name}-alb-to-api" })
}

resource "aws_lb" "this" {
  #checkov:skip=CKV_AWS_91:Access logs need a dedicated bucket and add cost; CloudFront is the single entry point and API logs are in CloudWatch.
  #checkov:skip=CKV_AWS_150:Deletion protection is off by default so the demo can be destroyed in one run (spec 09 story 27); alb_deletion_protection turns it on.
  #checkov:skip=CKV2_AWS_20:The CloudFront-to-ALB hop is plain HTTP by design (ADR-0011): there is no domain, so ACM cannot issue a certificate. CloudFront terminates TLS.
  #checkov:skip=CKV2_AWS_28:WAF in front of CloudFront is a noted future addition and out of scope (spec 09).
  name                       = local.name
  load_balancer_type         = "application"
  internal                   = false
  subnets                    = var.public_subnet_ids
  security_groups            = [aws_security_group.alb.id]
  drop_invalid_header_fields = true
  enable_deletion_protection = var.alb_deletion_protection
  idle_timeout               = 300 # Long enough for SSE chat streams between keep-alives.

  tags = merge(local.tags, { Name = local.name })
}

resource "aws_lb_target_group" "api" {
  #checkov:skip=CKV_AWS_378:The ALB-to-task hop stays inside the VPC over HTTP, like the CloudFront-to-ALB hop (ADR-0011).
  name                 = "${local.name}-api"
  target_type          = "ip"
  port                 = local.api_port
  protocol             = "HTTP"
  vpc_id               = var.vpc_id
  deregistration_delay = 30

  health_check {
    path                = "/api/health"
    matcher             = "200"
    interval            = 15
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  tags = merge(local.tags, { Name = "${local.name}-api" })
}

resource "aws_lb_listener" "http" {
  #checkov:skip=CKV_AWS_2:HTTP only by design: CloudFront terminates TLS and the origin hop is HTTP (ADR-0011).
  #checkov:skip=CKV_AWS_103:No TLS on this listener (ADR-0011), so there is no TLS policy to set.
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "fixed-response"

    fixed_response {
      content_type = "text/plain"
      message_body = "Forbidden"
      status_code  = "403"
    }
  }

  tags = merge(local.tags, { Name = "${local.name}-http" })
}

resource "aws_lb_listener_rule" "origin_header" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 1

  condition {
    http_header {
      http_header_name = var.origin_header_name
      values           = [terraform_data.origin_secret.output]
    }
  }

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  tags = merge(local.tags, { Name = "${local.name}-origin-header" })
}

# --- Services ----------------------------------------------------------------------------------------------------

# Egress rules are added below; the API's only ingress is the ALB.
resource "aws_security_group" "service" {
  #checkov:skip=CKV2_AWS_5:False positive: each group is attached to its ECS service's network configuration through for_each (asserted in tests).
  for_each = local.services

  name        = "${local.name}-${each.key}"
  description = "${each.key} tasks"
  vpc_id      = var.vpc_id

  tags = merge(local.tags, { Name = "${local.name}-${each.key}" })
}

locals {
  service_egress = merge(
    { for k in local.services : "${k}-https" => { service = k, target = "https", port = 443, cidr = "0.0.0.0/0", security_group = null } },
    { for k in setsubtract(local.services, ["beat"]) : "${k}-postgres" => { service = k, target = "postgres", port = var.database.port, cidr = null, security_group = var.database.security_group_id } },
    { for k in local.services : "${k}-redis" => { service = k, target = "redis", port = var.cache.port, cidr = null, security_group = var.cache.security_group_id } },
  )
}

# HTTPS reaches AWS APIs and model providers (through the NAT; S3 through its gateway endpoint). Data stores only for
# the services that use them: Beat never talks to Postgres.
resource "aws_vpc_security_group_egress_rule" "service" {
  for_each = local.service_egress

  security_group_id            = aws_security_group.service[each.value.service].id
  description                  = "${each.value.service} to ${each.value.target}"
  ip_protocol                  = "tcp"
  from_port                    = each.value.port
  to_port                      = each.value.port
  cidr_ipv4                    = each.value.cidr
  referenced_security_group_id = each.value.security_group

  tags = merge(local.tags, { Name = "${local.name}-${each.key}" })
}

resource "aws_vpc_security_group_ingress_rule" "api_from_alb" {
  security_group_id            = aws_security_group.service["api"].id
  description                  = "From the ALB"
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = local.api_port
  to_port                      = local.api_port

  tags = merge(local.tags, { Name = "${local.name}-api-from-alb" })
}

# --- Platform secrets created here: the origin header secret, the session-signing secret and the local key ---------

locals {
  platform_secret_descriptions = {
    origin-header = "Secret origin header value CloudFront sends to the ALB (ADR-0011)."
    session       = "Session-signing secret of ${local.name}, injected into the API."
    key-wrapper   = "LOCAL_KEY_WRAPPER_KEY of ${local.name}: signs widget tokens. Injected into every task."
  }
}

resource "aws_secretsmanager_secret" "platform" {
  #checkov:skip=CKV2_AWS_57:Rotation needs a rotation Lambda; the version inputs regenerate each secret instead (short-lived demo, spec 09).
  for_each = local.platform_secret_descriptions

  name                    = "${local.name}/${each.key}"
  description             = each.value
  kms_key_id              = var.data_key_arn
  recovery_window_in_days = 0

  tags = merge(local.tags, { Name = "${local.name}-${each.key}" })
}

resource "aws_secretsmanager_secret_version" "origin_header" {
  secret_id     = aws_secretsmanager_secret.platform["origin-header"].id
  secret_string = terraform_data.origin_secret.output
}

# The session-signing secret is 244 random bits written only through a write-only argument, so it never
# appears in state or plans. Bump session_secret_version for a new one.
resource "aws_secretsmanager_secret_version" "session" {
  secret_id                = aws_secretsmanager_secret.platform["session"].id
  secret_string_wo         = replace("${uuid()}${uuid()}", "-", "")
  secret_string_wo_version = var.session_secret_version
}

# LOCAL_KEY_WRAPPER_KEY must be 32 bytes, base64-encoded. Hex digits are base64 characters, so 43 of them and one
# padding character decode to 32 bytes; the 43 come from two version-4 UUIDs (crypto/rand), about 166 random bits.
# Written only through a write-only argument, like the session secret. Bump key_wrapper_secret_version for a new one;
# widget tokens signed with the old key stop working.
resource "aws_secretsmanager_secret_version" "key_wrapper" {
  secret_id                = aws_secretsmanager_secret.platform["key-wrapper"].id
  secret_string_wo         = "${substr(replace("${uuid()}${uuid()}", "-", ""), 0, 43)}="
  secret_string_wo_version = var.key_wrapper_secret_version
}

resource "aws_ecs_service" "this" {
  for_each = local.services

  name            = "${local.name}-${each.key}"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.this[each.key].arn
  desired_count   = var.desired_counts[each.key]

  capacity_provider_strategy {
    capacity_provider = local.capacity_providers[each.key]
    weight            = 1
  }

  # Beat is a singleton: stop the old scheduler before starting the new one. The others roll with no gap.
  deployment_maximum_percent         = each.key == "beat" ? 100 : 200
  deployment_minimum_healthy_percent = each.key == "beat" ? 0 : 100
  health_check_grace_period_seconds  = each.key == "api" ? 60 : null
  enable_execute_command             = false
  propagate_tags                     = "SERVICE"

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.service[each.key].id]
    assign_public_ip = false
  }

  dynamic "load_balancer" {
    for_each = each.key == "api" ? [aws_lb_target_group.api.arn] : []

    content {
      target_group_arn = load_balancer.value
      container_name   = "api"
      container_port   = local.api_port
    }
  }

  tags = merge(local.tags, { Name = "${local.name}-${each.key}" })

  # The capacity providers must be on the cluster before a service can name one.
  depends_on = [aws_ecs_cluster_capacity_providers.this]

  # An apply at a new image tag registers new task definitions but does not roll the services: the deploy
  # workflow first runs the migration task, then points each service at its new task definition and waits for
  # it to stabilise (spec 09 story 26). Terraform still sets the task definition when it creates a service.
  # The task count likewise: desired_counts starts each service, then autoscaling owns it (autoscaling.tf), so an
  # apply never undoes a scale-out (spec 22 story 21).
  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }
}
