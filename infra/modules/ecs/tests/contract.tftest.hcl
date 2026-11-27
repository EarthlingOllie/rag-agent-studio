# Module contract for the ecs module (ticket 09-04), at the module seam, with a mocked AWS provider.
# Runs that compare resource IDs or ARNs use `command = apply`: the mock provider only invents them at apply
# time, and it never calls AWS, so apply here creates nothing real.
mock_provider "aws" {
  mock_data "aws_region" {
    defaults = {
      region = "eu-west-2"
    }
  }

  # Two of CloudFront's origin-facing ranges (the real list has dozens and changes).
  mock_data "aws_ec2_managed_prefix_list" {
    defaults = {
      id = "pl-93a247fa"
      entries = [
        { cidr = "205.251.249.0/24", description = "" },
        { cidr = "130.176.0.0/18", description = "" },
      ]
    }
  }

  # Real-looking ARNs, so the policy documents built from them are valid JSON policies.
  mock_resource "aws_secretsmanager_secret" {
    defaults = {
      arn = "arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo-ecs/mocked-AbCdEf"
    }
  }

  mock_resource "aws_iam_role" {
    defaults = {
      arn = "arn:aws:iam::123456789012:role/studio-demo-ecs-mocked"
    }
  }

  mock_resource "aws_lb" {
    defaults = {
      arn = "arn:aws:elasticloadbalancing:eu-west-2:123456789012:loadbalancer/app/studio-demo-ecs/0123456789abcdef"
    }
  }

  mock_resource "aws_lb_target_group" {
    defaults = {
      arn = "arn:aws:elasticloadbalancing:eu-west-2:123456789012:targetgroup/studio-demo-ecs-api/0123456789abcdef"
    }
  }

  mock_resource "aws_lb_listener" {
    defaults = {
      arn = "arn:aws:elasticloadbalancing:eu-west-2:123456789012:listener/app/studio-demo-ecs/0123456789abcdef/0123456789abcdef"
    }
  }

  mock_resource "aws_appautoscaling_policy" {
    defaults = {
      arn = "arn:aws:autoscaling:eu-west-2:123456789012:scalingPolicy:00000000-0000-0000-0000-000000000000:resource/ecs/service/studio-demo-ecs/mocked:policyName/mocked"
    }
  }

  mock_resource "aws_cloudwatch_log_group" {
    defaults = {
      arn = "arn:aws:logs:eu-west-2:123456789012:log-group:/ecs/studio-demo-ecs/mocked"
    }
  }
}

# Distinct ARNs for the migration task's roles, so its task definition is shown to use them and not the services'
# (the mock provider otherwise gives every role the same ARN).
override_resource {
  target = aws_iam_role.migrate_task
  values = { arn = "arn:aws:iam::123456789012:role/studio-demo-ecs-migrate-task" }
}

override_resource {
  target = aws_iam_role.migrate_execution
  values = { arn = "arn:aws:iam::123456789012:role/studio-demo-ecs-migrate-execution" }
}

# The same for the seed task's roles (ticket 10-05).
override_resource {
  target = aws_iam_role.seed_task
  values = { arn = "arn:aws:iam::123456789012:role/studio-demo-ecs-seed-task" }
}

override_resource {
  target = aws_iam_role.seed_execution
  values = { arn = "arn:aws:iam::123456789012:role/studio-demo-ecs-seed-execution" }
}

# Its own ARN for the local key wrapper secret, so the policies are shown to name it (the mock gives every secret one ARN).
override_resource {
  target = aws_secretsmanager_secret.platform["key-wrapper"]
  values = { arn = "arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo-ecs/key-wrapper-DdDdDd" }
}

# The API's task role is the Bedrock trust principal the API is told about (BEDROCK_PLATFORM_PRINCIPAL).
override_resource {
  target = aws_iam_role.task["api"]
  values = { arn = "arn:aws:iam::123456789012:role/studio-demo-ecs-api-task" }
}

variables {
  studio_url           = "https://d111111abcdef8.cloudfront.net"
  name_prefix          = "studio-demo"
  tags                 = { Environment = "demo", Project = "rag-agent-studio" }
  vpc_id               = "vpc-0123456789abcdef0"
  vpc_cidr             = "10.20.0.0/16"
  public_subnet_ids    = ["subnet-0aaaaaaaaaaaaaaa1", "subnet-0bbbbbbbbbbbbbbb2"]
  private_subnet_ids   = ["subnet-0ccccccccccccccc3", "subnet-0ddddddddddddddd4"]
  image_repository_url = "123456789012.dkr.ecr.eu-west-2.amazonaws.com/rag-agent-studio/api"
  image_repository_arn = "arn:aws:ecr:eu-west-2:123456789012:repository/rag-agent-studio/api"
  image_tag            = "0123abc"
  documents_bucket_arn = "arn:aws:s3:::studio-demo-documents-123456789012"
  credentials_key_arn  = "arn:aws:kms:eu-west-2:123456789012:key/11111111-1111-1111-1111-111111111111"
  data_key_arn         = "arn:aws:kms:eu-west-2:123456789012:key/22222222-2222-2222-2222-222222222222"
  database = {
    address             = "studio-demo-database.abc.eu-west-2.rds.amazonaws.com"
    port                = 5432
    name                = "studio"
    username            = "studio"
    password_secret_arn = "arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo-database/master-password-AAAAAA"
    security_group_id   = "sg-0database00000001"
  }
  cache = {
    address               = "master.studio-demo-cache.abc.euw2.cache.amazonaws.com"
    port                  = 6379
    auth_token_secret_arn = "arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo-cache/auth-token-BBBBBB"
    security_group_id     = "sg-0cache00000000001"
  }
  queues = {
    general = {
      name = "studio-demo-queue-general"
      url  = "https://sqs.eu-west-2.amazonaws.com/123456789012/studio-demo-queue-general"
      arn  = "arn:aws:sqs:eu-west-2:123456789012:studio-demo-queue-general"
    }
    runs = {
      name = "studio-demo-queue-runs"
      url  = "https://sqs.eu-west-2.amazonaws.com/123456789012/studio-demo-queue-runs"
      arn  = "arn:aws:sqs:eu-west-2:123456789012:studio-demo-queue-runs"
    }
  }
}

run "runs_api_both_worker_pools_and_beat_on_arm64_fargate" {
  command = apply

  assert {
    condition     = keys(aws_ecs_service.this) == ["api", "beat", "worker-general", "worker-runs"]
    error_message = "There must be exactly four services: api, worker-general, worker-runs and beat (ticket 22-04)."
  }

  assert {
    condition     = alltrue([for k, s in aws_ecs_service.this : s.cluster == aws_ecs_cluster.this.id && s.task_definition == aws_ecs_task_definition.this[k].arn])
    error_message = "Each service must run its own task definition in the module's cluster."
  }

  assert {
    condition = alltrue([for t in aws_ecs_task_definition.this :
      t.requires_compatibilities == toset(["FARGATE"]) && t.network_mode == "awsvpc" &&
      t.runtime_platform[0].cpu_architecture == "ARM64" && t.runtime_platform[0].operating_system_family == "LINUX"
    ])
    error_message = "Every task must be an ARM64 Linux Fargate task."
  }

  assert {
    condition = { for k, t in aws_ecs_task_definition.this : k => [t.cpu, t.memory] } == {
      api              = ["512", "1024"]
      "worker-general" = ["2048", "8192"]
      "worker-runs"    = ["1024", "6144"]
      beat             = ["256", "512"]
    }
    error_message = "Task sizes must default to API 0.5 vCPU / 1 GB, general pool 2 vCPU / 8 GB (Docling) and runs pool 1 vCPU / 6 GB: ticket 22-04 measured two Run processes with the local Embedding Model and the Guardrail classifier at about 4.7 GB, past the spec's first guess of 4 GB."
  }

  assert {
    condition     = { for k, s in aws_ecs_service.this : k => s.desired_count } == { api = 1, "worker-general" = 1, "worker-runs" = 0, beat = 1 }
    error_message = "Each service starts with one task by default, except the runs pool, which starts at its scaling minimum of zero (ticket 22-05)."
  }
}

# Ticket 22-04: the general pool's jobs restart for free, so it runs on Fargate Spot; the runs pool's jobs are long and
# spend an Organisation's money, so it runs on regular Fargate (ADR-0021).
run "the_cluster_offers_fargate_and_fargate_spot" {
  command = apply

  assert {
    condition = (
      aws_ecs_cluster_capacity_providers.this.cluster_name == aws_ecs_cluster.this.name &&
      aws_ecs_cluster_capacity_providers.this.capacity_providers == toset(["FARGATE", "FARGATE_SPOT"])
    )
    error_message = "The cluster must have the Fargate and Fargate Spot capacity providers."
  }

  assert {
    condition     = [for s in aws_ecs_cluster_capacity_providers.this.default_capacity_provider_strategy : [s.capacity_provider, s.weight, s.base]] == [["FARGATE", 1, 0]]
    error_message = "A service that names no capacity provider must run on regular Fargate."
  }
}

run "the_general_pool_runs_on_spot_and_everything_else_on_regular_fargate" {
  command = plan

  assert {
    condition = { for k, s in aws_ecs_service.this : k => [for c in s.capacity_provider_strategy : [c.capacity_provider, c.weight]] } == {
      api              = [["FARGATE", 1]]
      "worker-general" = [["FARGATE_SPOT", 1]]
      "worker-runs"    = [["FARGATE", 1]]
      beat             = [["FARGATE", 1]]
    }
    error_message = "worker-general must use Fargate Spot by default; worker-runs, the API and Beat regular Fargate."
  }

  assert {
    condition     = output.capacity_providers == { for k, s in aws_ecs_service.this : k => one(s.capacity_provider_strategy).capacity_provider }
    error_message = "The module must output each service's capacity provider."
  }

  assert {
    condition     = alltrue([for s in aws_ecs_service.this : length(s.capacity_provider_strategy) == 1 && contains(aws_ecs_cluster_capacity_providers.this.capacity_providers, one(s.capacity_provider_strategy).capacity_provider)])
    error_message = "Each service must use exactly one of the cluster's capacity providers."
  }
}

run "worker_spot_false_moves_the_general_pool_to_regular_fargate" {
  command = plan

  variables {
    worker_spot = false
  }

  assert {
    condition     = alltrue([for s in aws_ecs_service.this : [for c in s.capacity_provider_strategy : c.capacity_provider] == ["FARGATE"]])
    error_message = "With worker_spot false every service, the general pool included, must run on regular Fargate (spec 22 story 10)."
  }
}

run "worker_tasks_get_two_minutes_to_stop" {
  command = plan

  assert {
    condition     = { for k, t in aws_ecs_task_definition.this : k => lookup(jsondecode(t.container_definitions)[0], "stopTimeout", null) } == { api = null, "worker-general" = 120, "worker-runs" = 120, beat = null }
    error_message = "Worker containers must have a two-minute stop timeout, so a short job finishes inside a Spot warning (spec 22 story 17); the API and Beat keep the default."
  }
}

run "task_sizes_are_variables" {
  command = plan

  variables {
    task_sizes = {
      api              = { cpu = 1024, memory = 2048 }
      "worker-general" = { cpu = 4096, memory = 16384 }
      "worker-runs"    = { cpu = 2048, memory = 6144 }
      beat             = { cpu = 256, memory = 1024 }
    }
  }

  assert {
    condition = { for k, t in aws_ecs_task_definition.this : k => [t.cpu, t.memory] } == {
      api              = ["1024", "2048"]
      "worker-general" = ["4096", "16384"]
      "worker-runs"    = ["2048", "6144"]
      beat             = ["256", "1024"]
    }
    error_message = "task_sizes must reach each task definition."
  }
}

run "each_service_runs_the_one_backend_image_with_its_own_command" {
  command = plan

  assert {
    condition     = alltrue([for t in aws_ecs_task_definition.this : jsondecode(t.container_definitions)[0].image == "123456789012.dkr.ecr.eu-west-2.amazonaws.com/rag-agent-studio/api:0123abc"])
    error_message = "Every service must run the backend image at the given tag."
  }

  assert {
    condition = { for k, t in aws_ecs_task_definition.this : k => jsondecode(t.container_definitions)[0].command } == {
      api              = ["python", "-m", "app.serve"]
      "worker-general" = ["celery", "-A", "app.worker.main", "--quiet", "worker", "--loglevel=INFO", "--concurrency=2", "--queues=studio-demo-queue-general"]
      "worker-runs"    = ["celery", "-A", "app.worker.main", "--quiet", "worker", "--loglevel=INFO", "--concurrency=2", "--queues=studio-demo-queue-runs"]
      beat             = ["celery", "-A", "app.worker.main", "--quiet", "beat", "--loglevel=INFO", "--schedule=/tmp/celerybeat-schedule"]
    }
    error_message = "Each service must run its own command, as in docker-compose.yml (migrations run as a separate task); each worker pool serves only its own queue."
  }
}

run "each_service_has_its_own_least_privilege_task_role" {
  command = apply

  assert {
    condition     = alltrue([for k, t in aws_ecs_task_definition.this : t.task_role_arn == aws_iam_role.task[k].arn]) && { for k, r in aws_iam_role.task : k => r.name } == { api = "studio-demo-ecs-api-task", "worker-general" = "studio-demo-ecs-worker-general-task", "worker-runs" = "studio-demo-ecs-worker-runs-task", beat = "studio-demo-ecs-beat-task" }
    error_message = "Each service must run with its own task role."
  }

  assert {
    condition = alltrue([for r in aws_iam_role.task : jsondecode(r.assume_role_policy) == {
      Version = "2012-10-17"
      Statement = [{
        Effect    = "Allow"
        Principal = { Service = "ecs-tasks.amazonaws.com" }
        Action    = "sts:AssumeRole"
        Condition = {
          StringEquals = { "aws:SourceAccount" = "123456789012" }
          ArnLike      = { "aws:SourceArn" = "arn:aws:ecs:eu-west-2:123456789012:*" }
        }
      }]
    }])
    error_message = "Only ECS tasks in this account and region may assume a task role."
  }

  assert {
    condition     = keys(aws_iam_role_policy.task) == ["api", "beat", "worker-general", "worker-runs"] && alltrue([for k, p in aws_iam_role_policy.task : p.role == aws_iam_role.task[k].id])
    error_message = "Each service's task role must have its own policy (Beat's first is sending to the general queue, ticket 22-02)."
  }

  assert {
    condition     = alltrue([for k in ["api", "beat", "worker-general", "worker-runs"] : output.task_role_policies[k] == jsondecode(aws_iam_role_policy.task[k].policy)])
    error_message = "The roles must use the policy documents asserted below."
  }
}

run "the_api_reads_documents_uses_the_credentials_key_and_assumes_roles_only_with_an_external_id" {
  command = plan

  assert {
    condition = output.task_role_policies.api == {
      Version = "2012-10-17"
      Statement = [
        {
          Sid      = "DocumentObjects"
          Effect   = "Allow"
          Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
          Resource = "arn:aws:s3:::studio-demo-documents-123456789012/*"
        },
        {
          Sid      = "DocumentsBucket"
          Effect   = "Allow"
          Action   = ["s3:ListBucket"]
          Resource = "arn:aws:s3:::studio-demo-documents-123456789012"
        },
        {
          Sid      = "DocumentsEncryption"
          Effect   = "Allow"
          Action   = ["kms:Decrypt", "kms:GenerateDataKey"]
          Resource = "arn:aws:kms:eu-west-2:123456789012:key/22222222-2222-2222-2222-222222222222"
        },
        {
          Sid      = "ProviderCredentialEnvelopes"
          Effect   = "Allow"
          Action   = ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey"]
          Resource = "arn:aws:kms:eu-west-2:123456789012:key/11111111-1111-1111-1111-111111111111"
        },
        {
          Sid      = "AssumeCustomerBedrockRolesWithExternalId"
          Effect   = "Allow"
          Action   = "sts:AssumeRole"
          Resource = "arn:aws:iam::*:role/*"
          Condition = {
            Null            = { "sts:ExternalId" = "false" }
            StringNotEquals = { "aws:ResourceAccount" = "123456789012" }
          }
        },
        {
          Sid    = "SendJobsToBothQueues"
          Effect = "Allow"
          Action = ["sqs:SendMessage"]
          Resource = [
            "arn:aws:sqs:eu-west-2:123456789012:studio-demo-queue-general",
            "arn:aws:sqs:eu-west-2:123456789012:studio-demo-queue-runs",
          ]
        },
      ]
    }
    error_message = "The API may use Document objects, the credentials key, assume other accounts' roles only with an external ID, and only send to the two queues."
  }
}

run "the_general_pool_reads_documents_decrypts_credentials_and_receives_only_general_jobs" {
  command = plan

  assert {
    condition = output.task_role_policies["worker-general"] == {
      Version = "2012-10-17"
      Statement = [
        {
          Sid      = "DocumentObjects"
          Effect   = "Allow"
          Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
          Resource = "arn:aws:s3:::studio-demo-documents-123456789012/*"
        },
        {
          Sid      = "DocumentsBucket"
          Effect   = "Allow"
          Action   = ["s3:ListBucket"]
          Resource = "arn:aws:s3:::studio-demo-documents-123456789012"
        },
        {
          Sid      = "DocumentsEncryption"
          Effect   = "Allow"
          Action   = ["kms:Decrypt", "kms:GenerateDataKey"]
          Resource = "arn:aws:kms:eu-west-2:123456789012:key/22222222-2222-2222-2222-222222222222"
        },
        {
          Sid      = "OpenProviderCredentialEnvelopes"
          Effect   = "Allow"
          Action   = ["kms:Decrypt"]
          Resource = "arn:aws:kms:eu-west-2:123456789012:key/11111111-1111-1111-1111-111111111111"
        },
        {
          Sid      = "ReceiveJobsFromItsOwnQueue"
          Effect   = "Allow"
          Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility", "sqs:GetQueueAttributes"]
          Resource = "arn:aws:sqs:eu-west-2:123456789012:studio-demo-queue-general"
        },
        {
          Sid    = "SendJobsToBothQueues"
          Effect = "Allow"
          Action = ["sqs:SendMessage"]
          Resource = [
            "arn:aws:sqs:eu-west-2:123456789012:studio-demo-queue-general",
            "arn:aws:sqs:eu-west-2:123456789012:studio-demo-queue-runs",
          ]
        },
        {
          Sid       = "ProtectItsOwnTaskFromScaleIn"
          Effect    = "Allow"
          Action    = ["ecs:GetTaskProtection", "ecs:UpdateTaskProtection"]
          Resource  = "arn:aws:ecs:eu-west-2:123456789012:task/studio-demo-ecs/*"
          Condition = { StringEquals = { "aws:ResourceTag/Name" = "studio-demo-ecs-worker-general" } }
        },
      ]
    }
    error_message = "The general pool ingests, re-embeds and deletes Documents (their objects and the data key), opens credential envelopes to embed with a Project's provider Embedding Model, receives only from the general queue and sends to both (spec 22 story 34), and protects its own tasks from scale-in (ticket 22-06)."
  }
}

run "the_runs_pool_only_decrypts_credentials_and_receives_only_runs_jobs" {
  command = plan

  assert {
    condition = output.task_role_policies["worker-runs"] == {
      Version = "2012-10-17"
      Statement = [
        {
          Sid      = "OpenProviderCredentialEnvelopes"
          Effect   = "Allow"
          Action   = ["kms:Decrypt"]
          Resource = "arn:aws:kms:eu-west-2:123456789012:key/11111111-1111-1111-1111-111111111111"
        },
        {
          Sid      = "ReceiveJobsFromItsOwnQueue"
          Effect   = "Allow"
          Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility", "sqs:GetQueueAttributes"]
          Resource = "arn:aws:sqs:eu-west-2:123456789012:studio-demo-queue-runs"
        },
        {
          Sid    = "SendJobsToBothQueues"
          Effect = "Allow"
          Action = ["sqs:SendMessage"]
          Resource = [
            "arn:aws:sqs:eu-west-2:123456789012:studio-demo-queue-general",
            "arn:aws:sqs:eu-west-2:123456789012:studio-demo-queue-runs",
          ]
        },
        {
          Sid       = "ProtectItsOwnTaskFromScaleIn"
          Effect    = "Allow"
          Action    = ["ecs:GetTaskProtection", "ecs:UpdateTaskProtection"]
          Resource  = "arn:aws:ecs:eu-west-2:123456789012:task/studio-demo-ecs/*"
          Condition = { StringEquals = { "aws:ResourceTag/Name" = "studio-demo-ecs-worker-runs" } }
        },
      ]
    }
    error_message = "Evaluation Runs and Suggestion runs never touch Documents' objects: the runs pool only opens credential envelopes (to call the Agent's model), receives only from the runs queue and sends to both (spec 22 story 34), and protects its own tasks from scale-in (ticket 22-06)."
  }
}

run "beat_may_only_send_to_the_general_queue" {
  command = plan

  assert {
    condition = output.task_role_policies.beat == {
      Version = "2012-10-17"
      Statement = [
        {
          Sid      = "SendJobsToTheGeneralQueue"
          Effect   = "Allow"
          Action   = ["sqs:SendMessage"]
          Resource = "arn:aws:sqs:eu-west-2:123456789012:studio-demo-queue-general"
        },
      ]
    }
    error_message = "Beat queues the scheduled jobs on the general queue and may do nothing else (spec 22 story 35)."
  }
}

run "every_service_is_told_the_queue_names_and_urls" {
  command = apply

  assert {
    condition = alltrue([for t in concat(values(aws_ecs_task_definition.this), [aws_ecs_task_definition.migrate, aws_ecs_task_definition.seed]) :
      { for e in jsondecode(t.container_definitions)[0].environment : e.name => e.value if startswith(e.name, "GENERAL_QUEUE_") || startswith(e.name, "RUNS_QUEUE_") } == {
        GENERAL_QUEUE_NAME = "studio-demo-queue-general"
        GENERAL_QUEUE_URL  = "https://sqs.eu-west-2.amazonaws.com/123456789012/studio-demo-queue-general"
        RUNS_QUEUE_NAME    = "studio-demo-queue-runs"
        RUNS_QUEUE_URL     = "https://sqs.eu-west-2.amazonaws.com/123456789012/studio-demo-queue-runs"
      }
    ])
    error_message = "Every container must be given the queues by setting, so no task needs to list or create them (spec 22 story 8)."
  }
}

run "rejects_a_queue_arn_that_is_not_sqs" {
  command = plan

  variables {
    queues = {
      general = { name = "studio-demo-queue-general", url = "https://sqs.eu-west-2.amazonaws.com/123456789012/studio-demo-queue-general", arn = "arn:aws:sns:eu-west-2:123456789012:studio-demo-queue-general" }
      runs    = { name = "studio-demo-queue-runs", url = "studio-demo-queue-runs", arn = "arn:aws:sqs:eu-west-2:123456789012:studio-demo-queue-runs" }
    }
  }

  expect_failures = [var.queues]
}

run "only_cloudfront_can_reach_the_alb" {
  command = apply

  assert {
    condition     = data.aws_ec2_managed_prefix_list.cloudfront.name == "com.amazonaws.global.cloudfront.origin-facing"
    error_message = "The ALB must look up CloudFront's managed origin-facing prefix list."
  }

  assert {
    condition = (
      aws_lb.this.load_balancer_type == "application" && aws_lb.this.internal == false &&
      aws_lb.this.subnets == toset(var.public_subnet_ids) && aws_lb.this.security_groups == toset([aws_security_group.alb.id]) &&
      aws_lb.this.drop_invalid_header_fields
    )
    error_message = "The ALB must sit in the public subnets behind only its own security group and drop invalid headers."
  }

  assert {
    condition = (
      aws_vpc_security_group_ingress_rule.alb.security_group_id == aws_security_group.alb.id &&
      aws_vpc_security_group_ingress_rule.alb.prefix_list_id == "pl-93a247fa" &&
      aws_vpc_security_group_ingress_rule.alb.cidr_ipv4 == null && aws_vpc_security_group_ingress_rule.alb.cidr_ipv6 == null &&
      aws_vpc_security_group_ingress_rule.alb.referenced_security_group_id == null &&
      aws_vpc_security_group_ingress_rule.alb.ip_protocol == "tcp" && aws_vpc_security_group_ingress_rule.alb.from_port == 80 && aws_vpc_security_group_ingress_rule.alb.to_port == 80
    )
    error_message = "The ALB security group must admit HTTP from the CloudFront prefix list and nothing else."
  }

  assert {
    condition     = length(aws_security_group.alb.ingress) == 0 && length(aws_security_group.alb.egress) == 0
    error_message = "The ALB security group must have no inline rules (rules are separate resources)."
  }

  assert {
    condition = (
      aws_vpc_security_group_egress_rule.alb_to_api.security_group_id == aws_security_group.alb.id &&
      aws_vpc_security_group_egress_rule.alb_to_api.referenced_security_group_id == aws_security_group.service["api"].id &&
      aws_vpc_security_group_egress_rule.alb_to_api.cidr_ipv4 == null &&
      aws_vpc_security_group_egress_rule.alb_to_api.from_port == 8000 && aws_vpc_security_group_egress_rule.alb_to_api.to_port == 8000
    )
    error_message = "The ALB may only talk to the API tasks on the API port."
  }

  assert {
    condition = (
      aws_vpc_security_group_ingress_rule.api_from_alb.security_group_id == aws_security_group.service["api"].id &&
      aws_vpc_security_group_ingress_rule.api_from_alb.referenced_security_group_id == aws_security_group.alb.id &&
      aws_vpc_security_group_ingress_rule.api_from_alb.from_port == 8000 && aws_vpc_security_group_ingress_rule.api_from_alb.to_port == 8000
    )
    error_message = "The API tasks must admit only the ALB, on the API port."
  }
}

# Spec 06: the Visitor's IP is taken from CloudFront's and the ALB's X-Forwarded-For entries, believed only from
# the trusted proxies. The ALB connects from inside the VPC and CloudFront from its origin-facing ranges (the only
# addresses the ALB admits); without both, every Visitor would share one per-IP rate limit.
run "the_api_trusts_the_alb_and_cloudfront_as_forwarding_proxies" {
  command = apply

  assert {
    condition     = local.environment.api.TRUSTED_PROXIES == "10.20.0.0/16,130.176.0.0/18,205.251.249.0/24"
    error_message = "The API must trust X-Forwarded-For from the VPC (the ALB) and CloudFront's origin-facing ranges."
  }

  assert {
    condition     = alltrue([for k in ["worker-general", "worker-runs", "beat"] : !contains(keys(local.environment[k]), "TRUSTED_PROXIES")])
    error_message = "Only the API serves requests, so only it is told the trusted proxies."
  }
}

run "rejects_a_vpc_cidr_that_is_not_a_cidr" {
  command = plan

  variables {
    vpc_cidr = "the-vpc"
  }

  expect_failures = [var.vpc_cidr]
}

run "the_alb_forwards_only_requests_carrying_the_secret_header" {
  command = apply

  assert {
    condition = (
      aws_lb_listener.http.load_balancer_arn == aws_lb.this.arn && aws_lb_listener.http.port == 80 && aws_lb_listener.http.protocol == "HTTP" &&
      length(aws_lb_listener.http.default_action) == 1 && aws_lb_listener.http.default_action[0].type == "fixed-response" &&
      aws_lb_listener.http.default_action[0].fixed_response[0].status_code == "403"
    )
    error_message = "Without the secret header, the listener must answer 403."
  }

  assert {
    condition = (
      aws_lb_listener_rule.origin_header.listener_arn == aws_lb_listener.http.arn &&
      length(aws_lb_listener_rule.origin_header.condition) == 1 &&
      one(aws_lb_listener_rule.origin_header.condition).http_header[0].http_header_name == "X-Origin-Verify" &&
      one(aws_lb_listener_rule.origin_header.condition).http_header[0].values == toset([output.origin_header_value])
    )
    error_message = "The only listener rule must match the secret origin header and its value."
  }

  assert {
    condition = (
      length(aws_lb_listener_rule.origin_header.action) == 1 &&
      aws_lb_listener_rule.origin_header.action[0].type == "forward" &&
      aws_lb_listener_rule.origin_header.action[0].target_group_arn == aws_lb_target_group.api.arn
    )
    error_message = "Requests with the secret header must be forwarded to the API."
  }

  assert {
    condition     = length(output.origin_header_value) == 64 && can(regex("^[0-9a-f]+$", output.origin_header_value)) && output.origin_header_name == "X-Origin-Verify"
    error_message = "The origin secret must be 256 random bits as hex, and both name and value are outputs for the cdn module."
  }

  assert {
    condition = (
      aws_lb_target_group.api.target_type == "ip" && aws_lb_target_group.api.port == 8000 && aws_lb_target_group.api.protocol == "HTTP" &&
      aws_lb_target_group.api.vpc_id == var.vpc_id && aws_lb_target_group.api.health_check[0].path == "/api/health"
    )
    error_message = "The target group must send HTTP to the API tasks' IPs and check /api/health."
  }

  assert {
    condition = (
      length(aws_ecs_service.this["api"].load_balancer) == 1 &&
      one(aws_ecs_service.this["api"].load_balancer).target_group_arn == aws_lb_target_group.api.arn &&
      one(aws_ecs_service.this["api"].load_balancer).container_name == "api" && one(aws_ecs_service.this["api"].load_balancer).container_port == 8000 &&
      alltrue([for k in ["worker-general", "worker-runs", "beat"] : length(aws_ecs_service.this[k].load_balancer) == 0])
    )
    error_message = "Only the API service sits behind the ALB."
  }

  assert {
    condition     = aws_secretsmanager_secret.platform["origin-header"].kms_key_id == var.data_key_arn && aws_secretsmanager_secret_version.origin_header.secret_string == output.origin_header_value
    error_message = "The origin header secret must also be kept in Secrets Manager, encrypted with the data key."
  }
}

run "origin_secret_version_rotates_the_header_value" {
  command = plan

  variables {
    origin_secret_version = 2
  }

  assert {
    condition     = terraform_data.origin_secret.triggers_replace == 2
    error_message = "origin_secret_version must regenerate the origin header secret."
  }
}

run "the_header_name_is_configurable" {
  command = plan

  variables {
    origin_header_name = "X-Studio-Origin"
  }

  assert {
    condition     = one(aws_lb_listener_rule.origin_header.condition).http_header[0].http_header_name == "X-Studio-Origin" && output.origin_header_name == "X-Studio-Origin"
    error_message = "origin_header_name must reach the listener rule and the output."
  }
}

run "secrets_are_injected_from_secrets_manager_and_never_set_as_plain_values" {
  command = apply

  assert {
    condition = { for k, t in aws_ecs_task_definition.this : k => { for e in jsondecode(t.container_definitions)[0].secrets : e.name => e.valueFrom } } == {
      api = {
        DATABASE_PASSWORD     = var.database.password_secret_arn
        REDIS_AUTH_TOKEN      = var.cache.auth_token_secret_arn
        SESSION_SECRET        = aws_secretsmanager_secret.platform["session"].arn
        LOCAL_KEY_WRAPPER_KEY = aws_secretsmanager_secret.platform["key-wrapper"].arn
      }
      "worker-general" = {
        DATABASE_PASSWORD     = var.database.password_secret_arn
        REDIS_AUTH_TOKEN      = var.cache.auth_token_secret_arn
        LOCAL_KEY_WRAPPER_KEY = aws_secretsmanager_secret.platform["key-wrapper"].arn
      }
      "worker-runs" = {
        DATABASE_PASSWORD     = var.database.password_secret_arn
        REDIS_AUTH_TOKEN      = var.cache.auth_token_secret_arn
        LOCAL_KEY_WRAPPER_KEY = aws_secretsmanager_secret.platform["key-wrapper"].arn
      }
      beat = {
        REDIS_AUTH_TOKEN      = var.cache.auth_token_secret_arn
        LOCAL_KEY_WRAPPER_KEY = aws_secretsmanager_secret.platform["key-wrapper"].arn
      }
    }
    error_message = "Each service must get only the secrets it needs, by reference to Secrets Manager."
  }

  assert {
    condition = alltrue(flatten([for t in aws_ecs_task_definition.this : [for e in jsondecode(t.container_definitions)[0].environment :
      length(regexall("PASSWORD|TOKEN|SECRET|KEY$", e.name)) == 0
    ]]))
    error_message = "No secret may be passed as a plain environment variable."
  }

  assert {
    condition = (
      !contains([for e in jsondecode(aws_ecs_task_definition.this["beat"].container_definitions)[0].environment : e.name], "OBJECT_STORE_BUCKET") &&
      !contains([for e in jsondecode(aws_ecs_task_definition.this["beat"].container_definitions)[0].environment : e.name], "KMS_KEY_ID") &&
      !contains([for e in jsondecode(aws_ecs_task_definition.this["beat"].container_definitions)[0].secrets : e.name], "DATABASE_PASSWORD")
    )
    error_message = "Beat learns nothing about Documents or the credentials key, and gets no database password."
  }

  assert {
    condition     = aws_secretsmanager_secret.platform["key-wrapper"].kms_key_id == var.data_key_arn && aws_secretsmanager_secret_version.key_wrapper.secret_id == aws_secretsmanager_secret.platform["key-wrapper"].id
    error_message = "The local key wrapper key must be stored encrypted with the data key."
  }

  assert {
    condition     = (aws_secretsmanager_secret_version.key_wrapper.secret_string == null || aws_secretsmanager_secret_version.key_wrapper.secret_string == "") && aws_secretsmanager_secret_version.key_wrapper.secret_string_wo_version == 1
    error_message = "The local key wrapper key must be written write-only, so it never reaches state."
  }

  assert {
    condition     = aws_secretsmanager_secret.platform["session"].kms_key_id == var.data_key_arn && aws_secretsmanager_secret_version.session.secret_id == aws_secretsmanager_secret.platform["session"].id
    error_message = "The session secret must be stored encrypted with the data key."
  }

  assert {
    condition     = (aws_secretsmanager_secret_version.session.secret_string == null || aws_secretsmanager_secret_version.session.secret_string == "") && aws_secretsmanager_secret_version.session.secret_string_wo_version == 1
    error_message = "The session secret must be written write-only, so it never reaches state."
  }
}

run "session_secret_version_bumps_the_write" {
  command = plan

  variables {
    session_secret_version = 3
  }

  assert {
    condition     = aws_secretsmanager_secret_version.session.secret_string_wo_version == 3
    error_message = "session_secret_version must reach Secrets Manager."
  }
}

run "a_logfire_token_is_injected_into_every_service_when_given" {
  command = plan

  variables {
    logfire_token_secret_arn = "arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo/logfire-CCCCCC"
  }

  assert {
    condition = alltrue([for t in aws_ecs_task_definition.this : contains(jsondecode(t.container_definitions)[0].secrets, {
      name      = "LOGFIRE_TOKEN"
      valueFrom = "arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo/logfire-CCCCCC"
    })])
    error_message = "Every service must get LOGFIRE_TOKEN from the given secret."
  }
}

run "no_logfire_token_without_a_secret" {
  command = plan

  assert {
    condition     = alltrue(flatten([for t in aws_ecs_task_definition.this : [for s in jsondecode(t.container_definitions)[0].secrets : s.name != "LOGFIRE_TOKEN"]]))
    error_message = "Without a Logfire secret, no service gets LOGFIRE_TOKEN."
  }
}

run "every_service_logs_to_its_own_log_group_with_retention" {
  command = apply

  assert {
    condition     = { for k, g in aws_cloudwatch_log_group.service : k => [g.name, g.retention_in_days] } == { api = ["/ecs/studio-demo-ecs/api", 14], "worker-general" = ["/ecs/studio-demo-ecs/worker-general", 14], "worker-runs" = ["/ecs/studio-demo-ecs/worker-runs", 14], beat = ["/ecs/studio-demo-ecs/beat", 14] }
    error_message = "Each service must have its own log group, kept for 14 days by default."
  }

  assert {
    condition = alltrue([for k, t in aws_ecs_task_definition.this : jsondecode(t.container_definitions)[0].logConfiguration == {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.service[k].name
        "awslogs-region"        = "eu-west-2"
        "awslogs-stream-prefix" = k
      }
    }])
    error_message = "Each container must send its (JSON) output to its own log group."
  }
}

run "log_retention_is_configurable" {
  command = plan

  variables {
    log_retention_days = 3
  }

  assert {
    condition     = alltrue([for g in aws_cloudwatch_log_group.service : g.retention_in_days == 3])
    error_message = "log_retention_days must reach every log group."
  }
}

run "containers_run_with_a_read_only_root_filesystem" {
  command = plan

  assert {
    condition = alltrue([for t in aws_ecs_task_definition.this :
      jsondecode(t.container_definitions)[0].readonlyRootFilesystem == true &&
      jsondecode(t.container_definitions)[0].mountPoints == [{ sourceVolume = "tmp", containerPath = "/tmp", readOnly = false }] &&
      [for v in t.volume : v.name] == ["tmp"]
    ])
    error_message = "Root filesystems must be read-only, with only /tmp writable (Beat keeps its schedule there)."
  }
}

run "each_service_has_its_own_least_privilege_execution_role" {
  command = apply

  assert {
    condition = (
      alltrue([for k, t in aws_ecs_task_definition.this : t.execution_role_arn == aws_iam_role.execution[k].arn]) &&
      { for k, r in aws_iam_role.execution : k => r.name } == { api = "studio-demo-ecs-api-execution", "worker-general" = "studio-demo-ecs-worker-general-execution", "worker-runs" = "studio-demo-ecs-worker-runs-execution", beat = "studio-demo-ecs-beat-execution" } &&
      alltrue([for r in aws_iam_role.execution : r.assume_role_policy == aws_iam_role.task["api"].assume_role_policy])
    )
    error_message = "Each service must start with its own execution role, assumable only by ECS tasks in this account."
  }

  assert {
    condition     = alltrue([for k, p in aws_iam_role_policy.execution : p.role == aws_iam_role.execution[k].id && jsondecode(p.policy) == output.execution_role_policies[k]])
    error_message = "The execution roles must use the policy documents asserted below."
  }

  assert {
    condition = output.execution_role_policies.beat == {
      Version = "2012-10-17"
      Statement = [
        {
          Sid      = "AuthenticateToEcr"
          Effect   = "Allow"
          Action   = "ecr:GetAuthorizationToken"
          Resource = "*"
        },
        {
          Sid      = "PullTheBackendImage"
          Effect   = "Allow"
          Action   = ["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"]
          Resource = "arn:aws:ecr:eu-west-2:123456789012:repository/rag-agent-studio/api"
        },
        {
          Sid      = "WriteOwnLogs"
          Effect   = "Allow"
          Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
          Resource = "${aws_cloudwatch_log_group.service["beat"].arn}:log-stream:*"
        },
        {
          Sid      = "ReadOwnSecrets"
          Effect   = "Allow"
          Action   = "secretsmanager:GetSecretValue"
          Resource = ["arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo-ecs/key-wrapper-DdDdDd", "arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo-cache/auth-token-BBBBBB"]
        },
        {
          Sid       = "DecryptSecretsThroughSecretsManager"
          Effect    = "Allow"
          Action    = "kms:Decrypt"
          Resource  = "arn:aws:kms:eu-west-2:123456789012:key/22222222-2222-2222-2222-222222222222"
          Condition = { StringEquals = { "kms:ViaService" = "secretsmanager.eu-west-2.amazonaws.com" } }
        },
      ]
    }
    error_message = "Beat's execution role may pull the image, write its own logs and read only the Redis token and the local key wrapper key."
  }

  assert {
    condition = output.execution_role_policies.api.Statement[3].Resource == [
      "arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo-database/master-password-AAAAAA",
      "arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo-ecs/key-wrapper-DdDdDd",
      "arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo-cache/auth-token-BBBBBB",
      aws_secretsmanager_secret.platform["session"].arn,
    ]
    error_message = "The API's execution role may read exactly the database password, Redis token, local key wrapper key and session secret."
  }

  assert {
    condition = alltrue([for k in ["worker-general", "worker-runs"] : output.execution_role_policies[k].Statement[3].Resource == [
      "arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo-database/master-password-AAAAAA",
      "arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo-ecs/key-wrapper-DdDdDd",
      "arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo-cache/auth-token-BBBBBB",
    ]])
    error_message = "Each worker pool's execution role may read exactly the database password, local key wrapper key and Redis token."
  }

  assert {
    condition = alltrue([for k, p in output.execution_role_policies :
      p.Statement[2].Resource == "${aws_cloudwatch_log_group.service[k].arn}:log-stream:*" && p.Statement[1].Resource == var.image_repository_arn
    ])
    error_message = "Each execution role may write only its own log group and pull only the backend image."
  }
}

run "services_reach_only_their_data_stores_and_https" {
  command = apply

  assert {
    condition = jsonencode({ for k, r in aws_vpc_security_group_egress_rule.service : k => [r.security_group_id, r.ip_protocol, r.from_port, r.to_port, r.cidr_ipv4, r.referenced_security_group_id] }) == jsonencode({
      "api-https"               = [aws_security_group.service["api"].id, "tcp", 443, 443, "0.0.0.0/0", null]
      "api-postgres"            = [aws_security_group.service["api"].id, "tcp", 5432, 5432, null, "sg-0database00000001"]
      "api-redis"               = [aws_security_group.service["api"].id, "tcp", 6379, 6379, null, "sg-0cache00000000001"]
      "beat-https"              = [aws_security_group.service["beat"].id, "tcp", 443, 443, "0.0.0.0/0", null]
      "beat-redis"              = [aws_security_group.service["beat"].id, "tcp", 6379, 6379, null, "sg-0cache00000000001"]
      "worker-general-https"    = [aws_security_group.service["worker-general"].id, "tcp", 443, 443, "0.0.0.0/0", null]
      "worker-general-postgres" = [aws_security_group.service["worker-general"].id, "tcp", 5432, 5432, null, "sg-0database00000001"]
      "worker-general-redis"    = [aws_security_group.service["worker-general"].id, "tcp", 6379, 6379, null, "sg-0cache00000000001"]
      "worker-runs-https"       = [aws_security_group.service["worker-runs"].id, "tcp", 443, 443, "0.0.0.0/0", null]
      "worker-runs-postgres"    = [aws_security_group.service["worker-runs"].id, "tcp", 5432, 5432, null, "sg-0database00000001"]
      "worker-runs-redis"       = [aws_security_group.service["worker-runs"].id, "tcp", 6379, 6379, null, "sg-0cache00000000001"]
    })
    error_message = "Services may reach HTTPS (AWS APIs and model providers), and only the data stores they use."
  }

  assert {
    condition = { for k, r in aws_vpc_security_group_egress_rule.service : k => r.description } == {
      "api-https"               = "api to https"
      "api-postgres"            = "api to postgres"
      "api-redis"               = "api to redis"
      "beat-https"              = "beat to https"
      "beat-redis"              = "beat to redis"
      "worker-general-https"    = "worker-general to https"
      "worker-general-postgres" = "worker-general to postgres"
      "worker-general-redis"    = "worker-general to redis"
      "worker-runs-https"       = "worker-runs to https"
      "worker-runs-postgres"    = "worker-runs to postgres"
      "worker-runs-redis"       = "worker-runs to redis"
    }
    error_message = "Each egress rule must say which service reaches what."
  }

  assert {
    condition     = alltrue([for sg in aws_security_group.service : length(sg.ingress) == 0 && length(sg.egress) == 0 && sg.vpc_id == var.vpc_id])
    error_message = "Service security groups must have no inline rules."
  }

  assert {
    condition     = output.service_security_group_ids == { for k, sg in aws_security_group.service : k => sg.id }
    error_message = "The module must output each service's security group, for the database and cache ingress rules."
  }

  assert {
    condition     = alltrue([for s in aws_ecs_service.this : one(s.network_configuration).assign_public_ip == false && one(s.network_configuration).subnets == toset(var.private_subnet_ids)])
    error_message = "Tasks must run in the private subnets without public IPs."
  }
}

run "deployments_roll_back_and_beat_never_runs_twice" {
  command = plan

  assert {
    condition     = alltrue([for s in aws_ecs_service.this : s.deployment_circuit_breaker[0].enable && s.deployment_circuit_breaker[0].rollback])
    error_message = "A failed deployment must roll back on its own."
  }

  assert {
    condition     = aws_ecs_service.this["beat"].deployment_maximum_percent == 100 && aws_ecs_service.this["beat"].deployment_minimum_healthy_percent == 0
    error_message = "A Beat deployment must stop the old scheduler before starting the new one."
  }

  assert {
    condition     = alltrue([for k in ["api", "worker-general", "worker-runs"] : aws_ecs_service.this[k].deployment_maximum_percent == 200 && aws_ecs_service.this[k].deployment_minimum_healthy_percent == 100])
    error_message = "API and worker pool deployments must start new tasks before stopping old ones."
  }

  assert {
    condition     = alltrue([for s in aws_ecs_service.this : s.enable_execute_command == false && s.propagate_tags == "SERVICE"])
    error_message = "No shell access into tasks, and tasks carry the service's tags."
  }
}

run "outputs_the_cluster_services_and_the_bedrock_trust_principal" {
  command = apply

  assert {
    condition     = output.cluster_name == "studio-demo-ecs" && aws_ecs_cluster.this.name == "studio-demo-ecs"
    error_message = "The cluster must be named from the prefix."
  }

  assert {
    condition     = output.service_names == { api = "studio-demo-ecs-api", "worker-general" = "studio-demo-ecs-worker-general", "worker-runs" = "studio-demo-ecs-worker-runs", beat = "studio-demo-ecs-beat" }
    error_message = "The module must output each service name, for the deploy workflow to wait on."
  }

  assert {
    condition     = output.api_task_role_arn == aws_iam_role.task["api"].arn && output.task_role_arns == { for k, r in aws_iam_role.task : k => r.arn }
    error_message = "The API task role ARN is the Bedrock external-ID trust principal (spec 09 outputs)."
  }

  assert {
    condition     = output.alb_dns_name == aws_lb.this.dns_name && output.log_group_names == { for k, g in aws_cloudwatch_log_group.service : k => g.name }
    error_message = "The module must output the ALB's DNS name and each log group."
  }
}

run "every_resource_carries_the_standard_tags" {
  command = plan

  assert {
    condition     = output.tags == { Environment = "demo", Project = "rag-agent-studio", Module = "ecs", ManagedBy = "terraform" }
    error_message = "Tags must merge the caller's tags with the module's own."
  }

  assert {
    condition = alltrue([for tags in concat(
      [aws_ecs_cluster.this.tags, aws_lb.this.tags, aws_lb_target_group.api.tags, aws_lb_listener.http.tags, aws_lb_listener_rule.origin_header.tags],
      [aws_security_group.alb.tags, aws_vpc_security_group_ingress_rule.alb.tags, aws_vpc_security_group_egress_rule.alb_to_api.tags, aws_vpc_security_group_ingress_rule.api_from_alb.tags],
      [for r in aws_ecs_task_definition.this : r.tags], [for r in aws_ecs_service.this : r.tags],
      [for r in aws_iam_role.task : r.tags], [for r in aws_iam_role.execution : r.tags],
      [for r in aws_security_group.service : r.tags], [for r in aws_vpc_security_group_egress_rule.service : r.tags],
      [for r in aws_cloudwatch_log_group.service : r.tags], [for r in aws_secretsmanager_secret.platform : r.tags],
    ) : alltrue([for key, value in output.tags : lookup(tags, key, null) == value])])
    error_message = "Every taggable resource must carry the standard tags."
  }

  assert {
    condition     = output.name == "studio-demo-ecs"
    error_message = "The ecs name must be derived from name_prefix."
  }
}

run "rejects_a_cpu_and_memory_pair_fargate_does_not_offer" {
  command = plan

  variables {
    task_sizes = {
      api              = { cpu = 512, memory = 512 }
      "worker-general" = { cpu = 2048, memory = 8192 }
      "worker-runs"    = { cpu = 1024, memory = 4096 }
      beat             = { cpu = 256, memory = 512 }
    }
  }

  expect_failures = [var.task_sizes]
}

run "rejects_an_unknown_cpu_value" {
  command = plan

  variables {
    task_sizes = {
      api              = { cpu = 300, memory = 1024 }
      "worker-general" = { cpu = 2048, memory = 8192 }
      "worker-runs"    = { cpu = 1024, memory = 4096 }
      beat             = { cpu = 256, memory = 512 }
    }
  }

  expect_failures = [var.task_sizes]
}

run "accepts_every_fargate_cpu_size" {
  command = plan

  variables {
    task_sizes = {
      api              = { cpu = 1024, memory = 8192 }
      "worker-general" = { cpu = 16384, memory = 122880 }
      "worker-runs"    = { cpu = 512, memory = 4096 }
      beat             = { cpu = 8192, memory = 61440 }
    }
  }

  assert {
    condition     = aws_ecs_task_definition.this["worker-general"].cpu == "16384" && aws_ecs_task_definition.this["beat"].memory == "61440"
    error_message = "The largest Fargate sizes must be accepted."
  }
}

run "accepts_4_vcpu_tasks" {
  command = plan

  variables {
    task_sizes = {
      api              = { cpu = 4096, memory = 30720 }
      "worker-general" = { cpu = 2048, memory = 16384 }
      "worker-runs"    = { cpu = 1024, memory = 8192 }
      beat             = { cpu = 256, memory = 2048 }
    }
  }

  assert {
    condition     = aws_ecs_task_definition.this["api"].memory == "30720"
    error_message = "4 vCPU with 30 GB must be accepted."
  }
}

run "rejects_a_missing_service_size" {
  command = plan

  variables {
    task_sizes = {
      api              = { cpu = 512, memory = 1024 }
      "worker-general" = { cpu = 2048, memory = 8192 }
      beat             = { cpu = 256, memory = 512 }
    }
  }

  expect_failures = [var.task_sizes]
}

run "rejects_two_beats" {
  command = plan

  variables {
    desired_counts = { api = 1, "worker-general" = 1, "worker-runs" = 1, beat = 2 }
  }

  expect_failures = [var.desired_counts]
}

run "rejects_a_negative_count" {
  command = plan

  variables {
    desired_counts = { api = 1, "worker-general" = 1, "worker-runs" = -1, beat = 1 }
  }

  expect_failures = [var.desired_counts]
}

run "rejects_the_latest_tag" {
  command = plan

  variables {
    image_tag = "latest"
  }

  expect_failures = [var.image_tag]
}

run "rejects_an_image_from_outside_ecr" {
  command = plan

  variables {
    image_repository_url = "docker.io/library/python"
  }

  expect_failures = [var.image_repository_url]
}

run "rejects_a_repository_arn_that_is_not_ecr" {
  command = plan

  variables {
    image_repository_arn = "arn:aws:s3:::rag-agent-studio"
  }

  expect_failures = [var.image_repository_arn]
}

run "rejects_keeping_logs_forever" {
  command = plan

  variables {
    log_retention_days = 0
  }

  expect_failures = [var.log_retention_days]
}

run "rejects_a_logfire_secret_that_is_not_a_secret_arn" {
  command = plan

  variables {
    logfire_token_secret_arn = "logfire-token"
  }

  expect_failures = [var.logfire_token_secret_arn]
}

run "rejects_a_header_name_with_spaces" {
  command = plan

  variables {
    origin_header_name = "X Origin"
  }

  expect_failures = [var.origin_header_name]
}

run "rejects_fractional_secret_versions" {
  command = plan

  variables {
    origin_secret_version  = 1.5
    session_secret_version = 0
  }

  expect_failures = [var.origin_secret_version, var.session_secret_version]
}

run "rejects_a_single_public_subnet" {
  command = plan

  variables {
    public_subnet_ids = ["subnet-0aaaaaaaaaaaaaaa1", "subnet-0aaaaaaaaaaaaaaa1"]
  }

  expect_failures = [var.public_subnet_ids]
}

run "rejects_no_private_subnets" {
  command = plan

  variables {
    private_subnet_ids = []
  }

  expect_failures = [var.private_subnet_ids]
}

run "rejects_arns_of_the_wrong_kind" {
  command = plan

  variables {
    documents_bucket_arn = "studio-demo-documents"
    credentials_key_arn  = "alias/credentials"
    data_key_arn         = "alias/data"
  }

  expect_failures = [var.documents_bucket_arn, var.credentials_key_arn, var.data_key_arn]
}

run "rejects_tags_without_project_and_environment" {
  command = plan

  variables {
    tags = { Environment = "demo" }
  }

  expect_failures = [var.tags]
}

run "rejects_an_invalid_prefix" {
  command = plan

  variables {
    name_prefix = "Studio_Demo"
  }

  expect_failures = [var.name_prefix]
}

run "alb_deletion_protection_is_off_for_the_demo_and_can_be_turned_on" {
  command = plan

  variables {
    alb_deletion_protection = true
  }

  assert {
    condition     = aws_lb.this.enable_deletion_protection
    error_message = "alb_deletion_protection must reach the ALB."
  }
}

run "the_demo_alb_can_be_destroyed_in_one_run" {
  command = plan

  assert {
    condition     = aws_lb.this.enable_deletion_protection == false && aws_lb.this.idle_timeout == 300
    error_message = "The demo ALB has no deletion protection, and its idle timeout outlasts SSE keep-alive gaps."
  }
}

# --- Migrations (ticket 09-06): a one-off task the deploy workflow runs, and waits on, before services roll ----------

run "migrations_run_as_a_one_off_task_on_the_backend_image" {
  command = apply

  assert {
    condition = (
      aws_ecs_task_definition.migrate.family == "studio-demo-ecs-migrate" &&
      jsondecode(aws_ecs_task_definition.migrate.container_definitions)[0].name == "migrate" &&
      jsondecode(aws_ecs_task_definition.migrate.container_definitions)[0].image == "123456789012.dkr.ecr.eu-west-2.amazonaws.com/rag-agent-studio/api:0123abc" &&
      jsondecode(aws_ecs_task_definition.migrate.container_definitions)[0].command == ["alembic", "upgrade", "head"]
    )
    error_message = "The migration task must run `alembic upgrade head` on the backend image at the given tag."
  }

  assert {
    condition = (
      aws_ecs_task_definition.migrate.requires_compatibilities == toset(["FARGATE"]) &&
      aws_ecs_task_definition.migrate.network_mode == "awsvpc" &&
      one(aws_ecs_task_definition.migrate.runtime_platform).cpu_architecture == "ARM64" &&
      aws_ecs_task_definition.migrate.cpu == "256" && aws_ecs_task_definition.migrate.memory == "512" &&
      jsondecode(aws_ecs_task_definition.migrate.container_definitions)[0].readonlyRootFilesystem == true
    )
    error_message = "The migration task must be a small ARM64 Fargate task with a read-only root filesystem."
  }

  assert {
    condition = { for s in jsondecode(aws_ecs_task_definition.migrate.container_definitions)[0].secrets : s.name => s.valueFrom } == {
      DATABASE_PASSWORD     = "arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo-database/master-password-AAAAAA"
      LOCAL_KEY_WRAPPER_KEY = aws_secretsmanager_secret.platform["key-wrapper"].arn
    }
    error_message = "The migration task gets the database password and the local key its settings require, and no Redis token."
  }

  assert {
    condition     = jsondecode(aws_ecs_task_definition.migrate.container_definitions)[0].logConfiguration.options["awslogs-group"] == "/ecs/studio-demo-ecs/migrate" && aws_cloudwatch_log_group.migrate.retention_in_days == 14
    error_message = "The migration task must log to its own log group, with the services' retention."
  }
}

run "the_migration_task_has_least_privilege_roles_and_reaches_only_postgres_and_https" {
  command = apply

  assert {
    condition = (
      aws_ecs_task_definition.migrate.task_role_arn == "arn:aws:iam::123456789012:role/studio-demo-ecs-migrate-task" &&
      aws_ecs_task_definition.migrate.execution_role_arn == "arn:aws:iam::123456789012:role/studio-demo-ecs-migrate-execution" &&
      aws_iam_role.migrate_task.name == "studio-demo-ecs-migrate-task" && aws_iam_role.migrate_execution.name == "studio-demo-ecs-migrate-execution" &&
      aws_iam_role.migrate_task.assume_role_policy == aws_iam_role.task["api"].assume_role_policy &&
      aws_iam_role.migrate_execution.assume_role_policy == aws_iam_role.task["api"].assume_role_policy
    )
    error_message = "The migration task must run with its own task and execution roles, assumable only by ECS tasks in this account."
  }

  assert {
    condition     = output.migration_task_role_policy == null
    error_message = "Migrations only talk to Postgres, so the migration task role gets no AWS permissions."
  }

  assert {
    condition = jsondecode(aws_iam_role_policy.migrate_execution.policy) == output.migration_execution_role_policy && output.migration_execution_role_policy == {
      Version = "2012-10-17"
      Statement = [
        {
          Sid      = "AuthenticateToEcr"
          Effect   = "Allow"
          Action   = "ecr:GetAuthorizationToken"
          Resource = "*"
        },
        {
          Sid      = "PullTheBackendImage"
          Effect   = "Allow"
          Action   = ["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"]
          Resource = "arn:aws:ecr:eu-west-2:123456789012:repository/rag-agent-studio/api"
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
          Resource = ["arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo-database/master-password-AAAAAA", "arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo-ecs/key-wrapper-DdDdDd"]
        },
        {
          Sid       = "DecryptSecretsThroughSecretsManager"
          Effect    = "Allow"
          Action    = "kms:Decrypt"
          Resource  = "arn:aws:kms:eu-west-2:123456789012:key/22222222-2222-2222-2222-222222222222"
          Condition = { StringEquals = { "kms:ViaService" = "secretsmanager.eu-west-2.amazonaws.com" } }
        },
      ]
    }
    error_message = "The migration execution role may pull the image, write its own logs and read only the database password and the local key wrapper key."
  }

  assert {
    condition = jsonencode({ for k, r in aws_vpc_security_group_egress_rule.migrate : k => [r.security_group_id, r.ip_protocol, r.from_port, r.to_port, r.cidr_ipv4, r.referenced_security_group_id] }) == jsonencode({
      https    = [aws_security_group.migrate.id, "tcp", 443, 443, "0.0.0.0/0", null]
      postgres = [aws_security_group.migrate.id, "tcp", 5432, 5432, null, "sg-0database00000001"]
    })
    error_message = "The migration task may reach HTTPS (image pulls, logs, secrets) and Postgres, nothing else."
  }

  assert {
    condition     = length(aws_security_group.migrate.ingress) == 0 && length(aws_security_group.migrate.egress) == 0 && aws_security_group.migrate.vpc_id == var.vpc_id
    error_message = "The migration security group must have no inline rules and no ingress."
  }
}

run "outputs_how_to_run_the_migration_task_and_each_service_task_definition" {
  command = apply

  assert {
    condition = output.migration_task == {
      task_definition_arn = aws_ecs_task_definition.migrate.arn
      container_name      = "migrate"
      subnet_ids          = var.private_subnet_ids
      security_group_id   = aws_security_group.migrate.id
    }
    error_message = "The deploy workflow needs the migration task definition, its container, private subnets and security group."
  }

  assert {
    condition     = output.migration_security_group_id == aws_security_group.migrate.id
    error_message = "The module must output the migration security group, for the database ingress rule."
  }

  assert {
    condition     = output.task_definition_arns == { for k, t in aws_ecs_task_definition.this : k => t.arn } && keys(output.task_definition_arns) == ["api", "beat", "worker-general", "worker-runs"]
    error_message = "The deploy workflow rolls each service onto its task definition at the new tag."
  }

  assert {
    condition = alltrue([for tags in [
      aws_ecs_task_definition.migrate.tags, aws_iam_role.migrate_task.tags, aws_iam_role.migrate_execution.tags,
      aws_security_group.migrate.tags, aws_cloudwatch_log_group.migrate.tags,
      aws_vpc_security_group_egress_rule.migrate["https"].tags, aws_vpc_security_group_egress_rule.migrate["postgres"].tags,
    ] : alltrue([for key, value in output.tags : lookup(tags, key, null) == value])])
    error_message = "The migration task's resources must carry the standard tags."
  }
}

run "the_migration_task_size_is_a_variable" {
  command = plan

  variables {
    migration_task_size = { cpu = 512, memory = 1024 }
  }

  assert {
    condition     = aws_ecs_task_definition.migrate.cpu == "512" && aws_ecs_task_definition.migrate.memory == "1024"
    error_message = "migration_task_size must size the migration task."
  }
}

run "rejects_a_migration_task_size_fargate_does_not_offer" {
  command = plan

  variables {
    migration_task_size = { cpu = 256, memory = 4096 }
  }

  expect_failures = [var.migration_task_size]
}

run "a_migration_logfire_token_is_injected_when_given" {
  command = plan

  variables {
    logfire_token_secret_arn = "arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo/logfire-CCCCCC"
  }

  assert {
    condition     = { for s in jsondecode(aws_ecs_task_definition.migrate.container_definitions)[0].secrets : s.name => s.valueFrom }["LOGFIRE_TOKEN"] == "arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo/logfire-CCCCCC"
    error_message = "Migrations must trace to Logfire like the services when a token is given."
  }
}

# The backend's Settings are loaded from task-settings.json by backend/tests/unit/test_aws_task_settings.py. This run
# pins the module to that file, so a container whose environment or secrets the backend cannot start with fails one
# of the two suites (ticket 09-06).
run "task_settings_match_the_recorded_contract" {
  command = apply

  assert {
    condition = jsonencode(merge(
      { for k, t in aws_ecs_task_definition.this : k => {
        environment = { for e in jsondecode(t.container_definitions)[0].environment : e.name => e.value }
        secrets     = sort([for e in jsondecode(t.container_definitions)[0].secrets : e.name])
      } },
      { for k, t in { migrate = aws_ecs_task_definition.migrate, seed = aws_ecs_task_definition.seed } : k => {
        environment           = { for e in jsondecode(t.container_definitions)[0].environment : e.name => e.value }
        secrets               = sort([for e in jsondecode(t.container_definitions)[0].secrets : e.name])
      } },
    )) == jsonencode({ for k, v in jsondecode(file("${path.module}/tests/task-settings.json")) : k => v if k != "_comment" })
    error_message = "The containers' environment and secret names must match infra/modules/ecs/tests/task-settings.json, which the backend tests load into Settings."
  }
}

run "demo_pages_turn_on_the_apis_demo_routes_only" {
  command = apply

  variables {
    demo_pages = true
  }

  assert {
    condition = { for k, t in aws_ecs_task_definition.this : k => contains(
      [for e in jsondecode(t.container_definitions)[0].environment : "${e.name}=${e.value}"], "DEMO_PAGES=true"
    ) } == { api = true, beat = false, "worker-general" = false, "worker-runs" = false }
    error_message = "demo_pages must set DEMO_PAGES=true on the API only (ticket 10-03); without it no container has it (task-settings.json)."
  }

  assert {
    condition     = !contains([for e in jsondecode(aws_ecs_task_definition.seed.container_definitions)[0].environment : e.name], "DEMO_PAGES")
    error_message = "The seed task (ticket 10-05) serves no demo pages, so it never gets DEMO_PAGES."
  }
}

run "rejects_a_studio_url_that_is_not_an_https_origin" {
  command = plan

  variables {
    studio_url = "http://d111111abcdef8.cloudfront.net/studio"
  }

  expect_failures = [var.studio_url]
}

# --- Seed in AWS (ticket 10-05): the demo data seeded by a one-off task the seed workflow runs ------------------------

run "the_seed_runs_as_a_one_off_task_on_the_backend_image" {
  command = apply

  assert {
    condition = (
      aws_ecs_task_definition.seed.family == "studio-demo-ecs-seed" &&
      jsondecode(aws_ecs_task_definition.seed.container_definitions)[0].name == "seed" &&
      jsondecode(aws_ecs_task_definition.seed.container_definitions)[0].image == "123456789012.dkr.ecr.eu-west-2.amazonaws.com/rag-agent-studio/api:0123abc" &&
      jsondecode(aws_ecs_task_definition.seed.container_definitions)[0].command == ["python", "-m", "app.seed"]
    )
    error_message = "The seed task must run `python -m app.seed` (the command behind `make seed`) on the backend image at the deployed tag."
  }

  assert {
    condition = (
      aws_ecs_task_definition.seed.requires_compatibilities == toset(["FARGATE"]) &&
      aws_ecs_task_definition.seed.network_mode == "awsvpc" &&
      one(aws_ecs_task_definition.seed.runtime_platform).cpu_architecture == "ARM64" &&
      aws_ecs_task_definition.seed.cpu == "1024" && aws_ecs_task_definition.seed.memory == "4096" &&
      jsondecode(aws_ecs_task_definition.seed.container_definitions)[0].readonlyRootFilesystem == true &&
      jsondecode(aws_ecs_task_definition.seed.container_definitions)[0].mountPoints == [{ sourceVolume = "tmp", containerPath = "/tmp", readOnly = false }]
    )
    error_message = "The seed task must be an ARM64 Fargate task with a read-only root filesystem and a scratch /tmp, sized for the in-process API and Guardrails."
  }

  assert {
    condition = { for s in jsondecode(aws_ecs_task_definition.seed.container_definitions)[0].secrets : s.name => s.valueFrom } == {
      DATABASE_PASSWORD     = "arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo-database/master-password-AAAAAA"
      REDIS_AUTH_TOKEN      = "arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo-cache/auth-token-BBBBBB"
      SESSION_SECRET        = aws_secretsmanager_secret.platform["session"].arn
      LOCAL_KEY_WRAPPER_KEY = aws_secretsmanager_secret.platform["key-wrapper"].arn
    }
    error_message = "The seed runs the API in process, so it gets the API's secrets: the database password, the Redis token, the session secret and the local key."
  }

  assert {
    condition     = jsondecode(aws_ecs_task_definition.seed.container_definitions)[0].logConfiguration.options == { "awslogs-group" = "/ecs/studio-demo-ecs/seed", "awslogs-region" = "eu-west-2", "awslogs-stream-prefix" = "seed" } && aws_cloudwatch_log_group.seed.retention_in_days == 14
    error_message = "The seed task must log to its own log group (the seed workflow prints it), with the services' retention."
  }
}

run "the_seed_task_has_its_own_roles_with_the_apis_data_access_and_no_bedrock" {
  command = apply

  assert {
    condition = (
      aws_ecs_task_definition.seed.task_role_arn == "arn:aws:iam::123456789012:role/studio-demo-ecs-seed-task" &&
      aws_ecs_task_definition.seed.execution_role_arn == "arn:aws:iam::123456789012:role/studio-demo-ecs-seed-execution" &&
      aws_iam_role.seed_task.name == "studio-demo-ecs-seed-task" && aws_iam_role.seed_execution.name == "studio-demo-ecs-seed-execution" &&
      aws_iam_role.seed_task.assume_role_policy == aws_iam_role.task["api"].assume_role_policy &&
      aws_iam_role.seed_execution.assume_role_policy == aws_iam_role.task["api"].assume_role_policy
    )
    error_message = "The seed task must run with its own task and execution roles, assumable only by ECS tasks in this account."
  }

  assert {
    condition = jsondecode(aws_iam_role_policy.seed_task.policy) == output.seed_task_role_policy && output.seed_task_role_policy == {
      Version = "2012-10-17"
      Statement = [
        {
          Sid      = "DocumentObjects"
          Effect   = "Allow"
          Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
          Resource = "arn:aws:s3:::studio-demo-documents-123456789012/*"
        },
        {
          Sid      = "DocumentsBucket"
          Effect   = "Allow"
          Action   = ["s3:ListBucket"]
          Resource = "arn:aws:s3:::studio-demo-documents-123456789012"
        },
        {
          Sid      = "DocumentsEncryption"
          Effect   = "Allow"
          Action   = ["kms:Decrypt", "kms:GenerateDataKey"]
          Resource = "arn:aws:kms:eu-west-2:123456789012:key/22222222-2222-2222-2222-222222222222"
        },
        {
          Sid      = "ProviderCredentialEnvelopes"
          Effect   = "Allow"
          Action   = ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey"]
          Resource = "arn:aws:kms:eu-west-2:123456789012:key/11111111-1111-1111-1111-111111111111"
        },
        {
          Sid    = "SendJobsToBothQueues"
          Effect = "Allow"
          Action = ["sqs:SendMessage"]
          Resource = [
            "arn:aws:sqs:eu-west-2:123456789012:studio-demo-queue-general",
            "arn:aws:sqs:eu-west-2:123456789012:studio-demo-queue-runs",
          ]
        },
      ]
    }
    error_message = "The seed uploads the demo Documents (and erases them on --reset), seals the demo credential and queues the demo Documents' ingestion for the general pool, as the API does; it never assumes customer Bedrock roles."
  }

  assert {
    condition = jsondecode(aws_iam_role_policy.seed_execution.policy) == output.seed_execution_role_policy && output.seed_execution_role_policy == {
      Version = "2012-10-17"
      Statement = [
        {
          Sid      = "AuthenticateToEcr"
          Effect   = "Allow"
          Action   = "ecr:GetAuthorizationToken"
          Resource = "*"
        },
        {
          Sid      = "PullTheBackendImage"
          Effect   = "Allow"
          Action   = ["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"]
          Resource = "arn:aws:ecr:eu-west-2:123456789012:repository/rag-agent-studio/api"
        },
        {
          Sid      = "WriteOwnLogs"
          Effect   = "Allow"
          Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
          Resource = "${aws_cloudwatch_log_group.seed.arn}:log-stream:*"
        },
        {
          Sid    = "ReadOwnSecrets"
          Effect = "Allow"
          Action = "secretsmanager:GetSecretValue"
          Resource = [
            "arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo-database/master-password-AAAAAA",
            "arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo-ecs/key-wrapper-DdDdDd",
            "arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo-cache/auth-token-BBBBBB",
            aws_secretsmanager_secret.platform["session"].arn,
          ]
        },
        {
          Sid       = "DecryptSecretsThroughSecretsManager"
          Effect    = "Allow"
          Action    = "kms:Decrypt"
          Resource  = "arn:aws:kms:eu-west-2:123456789012:key/22222222-2222-2222-2222-222222222222"
          Condition = { StringEquals = { "kms:ViaService" = "secretsmanager.eu-west-2.amazonaws.com" } }
        },
      ]
    }
    error_message = "The seed execution role may pull the image, write its own logs and read only the seed's secrets."
  }
}

run "the_seed_task_reaches_only_https_postgres_and_redis" {
  command = apply

  assert {
    condition = jsonencode({ for k, r in aws_vpc_security_group_egress_rule.seed : k => [r.security_group_id, r.ip_protocol, r.from_port, r.to_port, r.cidr_ipv4, r.referenced_security_group_id] }) == jsonencode({
      https    = [aws_security_group.seed.id, "tcp", 443, 443, "0.0.0.0/0", null]
      postgres = [aws_security_group.seed.id, "tcp", 5432, 5432, null, "sg-0database00000001"]
      redis    = [aws_security_group.seed.id, "tcp", 6379, 6379, null, "sg-0cache00000000001"]
    })
    error_message = "The seed task may reach HTTPS (S3, KMS, logs, secrets), Postgres and Redis (it queues ingestion for the worker), nothing else."
  }

  assert {
    condition     = length(aws_security_group.seed.ingress) == 0 && length(aws_security_group.seed.egress) == 0 && aws_security_group.seed.vpc_id == var.vpc_id
    error_message = "The seed security group must have no inline rules and no ingress."
  }
}

run "outputs_how_to_run_the_seed_task" {
  command = apply

  assert {
    condition = output.seed_task == {
      task_definition_arn = aws_ecs_task_definition.seed.arn
      container_name      = "seed"
      subnet_ids          = var.private_subnet_ids
      security_group_id   = aws_security_group.seed.id
      log_group_name      = "/ecs/studio-demo-ecs/seed"
      log_stream_prefix   = "seed"
    }
    error_message = "The seed workflow needs the seed task definition, its container, private subnets, security group and where it logs."
  }

  assert {
    condition     = output.seed_security_group_id == aws_security_group.seed.id
    error_message = "The module must output the seed security group, for the database and cache ingress rules."
  }

  assert {
    condition = alltrue([for tags in [
      aws_ecs_task_definition.seed.tags, aws_iam_role.seed_task.tags, aws_iam_role.seed_execution.tags,
      aws_security_group.seed.tags, aws_cloudwatch_log_group.seed.tags,
      aws_vpc_security_group_egress_rule.seed["https"].tags, aws_vpc_security_group_egress_rule.seed["postgres"].tags,
      aws_vpc_security_group_egress_rule.seed["redis"].tags,
    ] : alltrue([for key, value in output.tags : lookup(tags, key, null) == value])])
    error_message = "The seed task's resources must carry the standard tags."
  }
}

run "the_seed_task_size_is_a_variable" {
  command = plan

  variables {
    seed_task_size = { cpu = 2048, memory = 8192 }
  }

  assert {
    condition     = aws_ecs_task_definition.seed.cpu == "2048" && aws_ecs_task_definition.seed.memory == "8192"
    error_message = "seed_task_size must size the seed task."
  }
}

run "rejects_a_seed_task_size_fargate_does_not_offer" {
  command = plan

  variables {
    seed_task_size = { cpu = 1024, memory = 1024 }
  }

  expect_failures = [var.seed_task_size]
}

run "a_seed_logfire_token_is_injected_when_given" {
  command = plan

  variables {
    logfire_token_secret_arn = "arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo/logfire-CCCCCC"
  }

  assert {
    condition     = { for s in jsondecode(aws_ecs_task_definition.seed.container_definitions)[0].secrets : s.name => s.valueFrom }["LOGFIRE_TOKEN"] == "arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo/logfire-CCCCCC"
    error_message = "The seed task must trace to Logfire like the services when a token is given."
  }
}

# --- Autoscaling (ticket 22-05): the API on CPU, the worker pools on their queue's jobs, Beat fixed --------------------

run "the_api_and_both_worker_pools_are_scalable_targets_with_their_default_bounds" {
  command = apply

  assert {
    condition = { for k, t in aws_appautoscaling_target.this : k => [t.min_capacity, t.max_capacity] } == {
      api              = [1, 3]
      "worker-general" = [1, 3]
      "worker-runs"    = [0, 2]
    }
    error_message = "api scales 1 to 3, worker-general 1 to 3 and worker-runs 0 to 2 by default; beat has no scalable target (spec 22)."
  }

  assert {
    condition = alltrue([for k, t in aws_appautoscaling_target.this : (
      t.service_namespace == "ecs" &&
      t.scalable_dimension == "ecs:service:DesiredCount" &&
      t.resource_id == "service/${aws_ecs_cluster.this.name}/${aws_ecs_service.this[k].name}"
    )])
    error_message = "Each scalable target must be its own ECS service's desired count."
  }

  assert {
    condition     = output.scalable_targets["worker-runs"] == { resource_id = "service/studio-demo-ecs/studio-demo-ecs-worker-runs", min = 0, max = 2 }
    error_message = "The module must output each scalable target's resource ID and bounds (the scaling script reads them)."
  }
}

run "the_runs_pool_scales_to_zero" {
  command = plan

  assert {
    condition     = aws_appautoscaling_target.this["worker-runs"].min_capacity == 0 && var.desired_counts["worker-runs"] == 0
    error_message = "The runs pool's minimum and starting count must be zero, so it costs nothing between Runs (spec 22 story 13)."
  }
}

run "the_api_tracks_average_cpu" {
  command = plan

  assert {
    condition = (
      aws_appautoscaling_policy.api_cpu.policy_type == "TargetTrackingScaling" &&
      one(aws_appautoscaling_policy.api_cpu.target_tracking_scaling_policy_configuration).target_value == 60 &&
      one(one(aws_appautoscaling_policy.api_cpu.target_tracking_scaling_policy_configuration).predefined_metric_specification).predefined_metric_type == "ECSServiceAverageCPUUtilization"
    )
    error_message = "The API must track average CPU, at 60% by default (spec 22 story 19)."
  }

  assert {
    condition = [
      one(aws_appautoscaling_policy.api_cpu.target_tracking_scaling_policy_configuration).scale_out_cooldown,
      one(aws_appautoscaling_policy.api_cpu.target_tracking_scaling_policy_configuration).scale_in_cooldown,
    ] == [60, 300]
    error_message = "The API scales out after a minute's cooldown and in after five by default."
  }
}

run "each_worker_pool_scales_on_its_queues_waiting_plus_in_flight_jobs" {
  command = plan

  assert {
    condition = { for k, a in aws_cloudwatch_metric_alarm.worker_jobs : k => {
      metrics                                     = sort([for q in a.metric_query : "${one(q.metric).namespace}/${one(q.metric).metric_name}/${one(q.metric).dimensions["QueueName"]}/${one(q.metric).stat}/${one(q.metric).period}" if length(q.metric) > 0])
      expression                                  = one([for q in a.metric_query : q.expression if q.return_data == true])
      } } == { for k, queue in { "worker-general" = "studio-demo-queue-general", "worker-runs" = "studio-demo-queue-runs" } : k => {
      metrics = sort([
        "AWS/SQS/ApproximateNumberOfMessagesNotVisible/${queue}/Maximum/60",
        "AWS/SQS/ApproximateNumberOfMessagesVisible/${queue}/Maximum/60",
      ])
      expression = "waiting + in_flight"
    } }
    error_message = "Each pool must scale on its own queue's waiting (visible) plus in-flight (not visible) messages, so jobs being worked on count too (spec 22 story 18)."
  }

  assert {
    condition     = { for k, a in aws_cloudwatch_metric_alarm.worker_idle : k => one([for q in a.metric_query : q.expression if q.return_data == true]) } == { "worker-general" = "waiting + in_flight", "worker-runs" = "waiting + in_flight" }
    error_message = "A pool is idle only when its queue has neither waiting nor in-flight jobs, so it never scales in under a running job."
  }
}

run "a_worker_pool_steps_up_one_task_per_slots_worth_of_jobs" {
  command = plan

  assert {
    condition = alltrue([for k, a in aws_cloudwatch_metric_alarm.worker_jobs : (
      a.comparison_operator == "GreaterThanOrEqualToThreshold" && a.threshold == 1 && a.evaluation_periods == 1 &&
      a.treat_missing_data == "notBreaching" && a.alarm_actions == toset([aws_appautoscaling_policy.worker_jobs[k].arn])
    )])
    error_message = "A pool's jobs alarm fires as soon as its queue holds a job, and drives its jobs policy."
  }

  assert {
    condition = jsonencode({ for k, p in aws_appautoscaling_policy.worker_jobs : k => sort([
      for s in one(p.step_scaling_policy_configuration).step_adjustment : "${coalesce(s.metric_interval_lower_bound, "-inf")}..${coalesce(s.metric_interval_upper_bound, "inf")}=${s.scaling_adjustment}"
      ]) }) == jsonencode({
      # Bounds are relative to the threshold of one job: 1-2 jobs one task, 3-4 two, 5 or more three (two slots a task).
      "worker-general" = ["0..2=1", "2..4=2", "4..inf=3"]
      "worker-runs"    = ["0..2=1", "2..inf=2"]
    })
    error_message = "Above zero, a pool runs one task per two jobs (the slots a task has), up to its maximum: worker-runs goes from zero to one as soon as its queue holds anything."
  }

  assert {
    condition = alltrue([for k, p in aws_appautoscaling_policy.worker_jobs : (
      p.policy_type == "StepScaling" && one(p.step_scaling_policy_configuration).adjustment_type == "ExactCapacity" &&
      one(p.step_scaling_policy_configuration).cooldown == 60
    )])
    error_message = "The jobs policy sets the pool's exact task count, with a minute's cooldown by default."
  }
}

run "a_worker_pool_returns_to_its_minimum_after_its_queue_has_been_empty_for_five_minutes" {
  command = plan

  assert {
    condition = alltrue([for k, a in aws_cloudwatch_metric_alarm.worker_idle : (
      a.comparison_operator == "LessThanThreshold" && a.threshold == 1 && a.evaluation_periods == 5 &&
      a.treat_missing_data == "breaching" && a.alarm_actions == toset([aws_appautoscaling_policy.worker_idle[k].arn])
    )])
    error_message = "A pool's idle alarm fires once its queue has held no job for five minutes (SQS sends no data for an idle queue, which counts as empty)."
  }

  assert {
    condition = jsonencode({ for k, p in aws_appautoscaling_policy.worker_idle : k => sort([
      for s in one(p.step_scaling_policy_configuration).step_adjustment : "${coalesce(s.metric_interval_lower_bound, "-inf")}..${coalesce(s.metric_interval_upper_bound, "inf")}=${s.scaling_adjustment}"
    ]) }) == jsonencode({ "worker-general" = ["-inf..0=1"], "worker-runs" = ["-inf..0=0"] })
    error_message = "An idle pool goes back to its minimum: worker-runs to zero, worker-general to one."
  }

  assert {
    condition     = alltrue([for k, p in aws_appautoscaling_policy.worker_idle : one(p.step_scaling_policy_configuration).adjustment_type == "ExactCapacity" && one(p.step_scaling_policy_configuration).cooldown == 300])
    error_message = "The idle policy sets the pool's minimum exactly, with a five-minute cooldown by default."
  }
}

run "every_minimum_maximum_target_and_cooldown_is_a_variable" {
  command = plan

  variables {
    scaling = {
      api              = { min = 2, max = 6, cpu_target = 45, scale_out_cooldown = 30, scale_in_cooldown = 600 }
      "worker-general" = { min = 2, max = 4, jobs_per_task = 3, scale_out_cooldown = 90, scale_in_cooldown = 120, idle_minutes = 10 }
      "worker-runs"    = { min = 0, max = 1, jobs_per_task = 1, scale_out_cooldown = 0, scale_in_cooldown = 60, idle_minutes = 3 }
    }
    desired_counts = { api = 2, "worker-general" = 2, "worker-runs" = 0, beat = 1 }
  }

  assert {
    condition = { for k, t in aws_appautoscaling_target.this : k => [t.min_capacity, t.max_capacity] } == {
      api = [2, 6], "worker-general" = [2, 4], "worker-runs" = [0, 1]
    }
    error_message = "scaling must set each target's minimum and maximum."
  }

  assert {
    condition = [
      one(aws_appautoscaling_policy.api_cpu.target_tracking_scaling_policy_configuration).target_value,
      one(aws_appautoscaling_policy.api_cpu.target_tracking_scaling_policy_configuration).scale_out_cooldown,
      one(aws_appautoscaling_policy.api_cpu.target_tracking_scaling_policy_configuration).scale_in_cooldown,
    ] == [45, 30, 600]
    error_message = "scaling.api must set the CPU target and both cooldowns."
  }

  assert {
    condition = jsonencode({ for k, p in aws_appautoscaling_policy.worker_jobs : k => sort([
      for s in one(p.step_scaling_policy_configuration).step_adjustment : "${coalesce(s.metric_interval_lower_bound, "-inf")}..${coalesce(s.metric_interval_upper_bound, "inf")}=${s.scaling_adjustment}"
    ]) }) == jsonencode({ "worker-general" = ["0..3=1", "3..6=2", "6..9=3", "9..inf=4"], "worker-runs" = ["0..inf=1"] })
    error_message = "scaling's jobs_per_task and max must set the steps."
  }

  assert {
    condition = (
      { for k, p in aws_appautoscaling_policy.worker_jobs : k => one(p.step_scaling_policy_configuration).cooldown } == { "worker-general" = 90, "worker-runs" = 0 } &&
      { for k, p in aws_appautoscaling_policy.worker_idle : k => one(p.step_scaling_policy_configuration).cooldown } == { "worker-general" = 120, "worker-runs" = 60 } &&
      { for k, a in aws_cloudwatch_metric_alarm.worker_idle : k => a.evaluation_periods } == { "worker-general" = 10, "worker-runs" = 3 } &&
      { for k, p in aws_appautoscaling_policy.worker_idle : k => one(one(p.step_scaling_policy_configuration).step_adjustment).scaling_adjustment } == { "worker-general" = 2, "worker-runs" = 0 }
    )
    error_message = "scaling must set the workers' cooldowns, idle time and the minimum an idle pool returns to."
  }

  assert {
    condition = { for k in ["worker-general", "worker-runs"] : k => one([for a in jsondecode(aws_ecs_task_definition.this[k].container_definitions)[0].command : a if startswith(a, "--concurrency=")]) } == {
      "worker-general" = "--concurrency=3", "worker-runs" = "--concurrency=1"
    }
    error_message = "A worker runs as many jobs at once as the slots its pool scales by (jobs_per_task)."
  }
}

run "rejects_a_general_pool_that_scales_to_zero" {
  command = plan

  variables {
    scaling = { "worker-general" = { min = 0 } }
  }

  expect_failures = [var.scaling]
}

run "rejects_a_maximum_below_the_minimum" {
  command = plan

  variables {
    scaling = { api = { min = 3, max = 2 } }
  }

  expect_failures = [var.scaling]
}

run "rejects_a_starting_count_outside_the_scaling_bounds" {
  command = plan

  variables {
    desired_counts = { api = 4, "worker-general" = 1, "worker-runs" = 0, beat = 1 }
  }

  expect_failures = [var.desired_counts]
}

# A state of its own, so these two runs create the services fresh and then change the counts.
run "terraform_sets_each_task_count_when_it_creates_the_service" {
  command   = apply
  state_key = "task_counts"

  variables {
    desired_counts = { api = 2, "worker-general" = 3, "worker-runs" = 1, beat = 0 }
  }

  assert {
    condition     = { for k, s in aws_ecs_service.this : k => s.desired_count } == { api = 2, "worker-general" = 3, "worker-runs" = 1, beat = 0 }
    error_message = "desired_counts must set each service's task count when the service is created."
  }
}

run "terraform_ignores_task_counts_after_creation_so_an_apply_keeps_a_scale_out" {
  command   = plan
  state_key = "task_counts"

  variables {
    desired_counts = { api = 1, "worker-general" = 1, "worker-runs" = 0, beat = 1 }
  }

  assert {
    condition     = { for k, s in aws_ecs_service.this : k => s.desired_count } == { api = 2, "worker-general" = 3, "worker-runs" = 1, beat = 0 }
    error_message = "Once a service exists, autoscaling owns its task count: Terraform must ignore desired_count changes (spec 22 story 21)."
  }
}

# --- Scale-in protection (ticket 22-06): a worker protects its own task while it holds a job --------------------------

run "only_the_worker_pools_may_set_task_protection_and_only_on_their_own_tasks" {
  command = plan

  assert {
    condition = { for k, p in output.task_role_policies : k => [for st in p.Statement : st.Resource if contains(flatten([st.Action]), "ecs:UpdateTaskProtection")] } == {
      api              = []
      beat             = []
      "worker-general" = ["arn:aws:ecs:eu-west-2:123456789012:task/studio-demo-ecs/*"]
      "worker-runs"    = ["arn:aws:ecs:eu-west-2:123456789012:task/studio-demo-ecs/*"]
    }
    error_message = "Only the worker pools may set task protection, on tasks in this cluster only."
  }

  assert {
    condition = alltrue([for k in ["worker-general", "worker-runs"] : (
      one([for st in output.task_role_policies[k].Statement : st.Condition if st.Sid == "ProtectItsOwnTaskFromScaleIn"]) == { StringEquals = { "aws:ResourceTag/Name" = aws_ecs_service.this[k].tags["Name"] } } &&
      aws_ecs_service.this[k].propagate_tags == "SERVICE"
    )])
    error_message = "A pool may protect only tasks carrying its own service's Name tag (propagated from the service), so one pool can't unprotect the other's tasks; the ECS agent's endpoint acts on the calling task alone."
  }
}

# Ticket 23-02: inputs a local environment needs to differ from the demo without the module branching on it.
run "cpu_architecture_reaches_every_task_definition" {
  command = plan

  variables {
    cpu_architecture = "X86_64"
  }

  assert {
    condition = alltrue([for t in concat(values(aws_ecs_task_definition.this), [aws_ecs_task_definition.migrate, aws_ecs_task_definition.seed]) :
      one(t.runtime_platform).cpu_architecture == "X86_64" && one(t.runtime_platform).operating_system_family == "LINUX"
    ])
    error_message = "cpu_architecture must reach every task definition: the four services, the migration and the seed task (23-01: an emulator on an Intel host refuses ARM64 tasks)."
  }

  assert {
    condition     = output.cpu_architecture == "X86_64"
    error_message = "The module must report the architecture its task definitions run on."
  }
}

run "cpu_architecture_defaults_to_arm64_everywhere" {
  command = plan

  assert {
    condition = alltrue([for t in concat(values(aws_ecs_task_definition.this), [aws_ecs_task_definition.migrate, aws_ecs_task_definition.seed]) :
      one(t.runtime_platform).cpu_architecture == "ARM64"
    ])
    error_message = "Every task definition must stay ARM64 (Graviton) by default."
  }

  assert {
    condition     = output.cpu_architecture == "ARM64"
    error_message = "The module must report ARM64 by default."
  }
}

run "rejects_an_unknown_cpu_architecture" {
  command = plan

  variables {
    cpu_architecture = "arm64"
  }

  expect_failures = [var.cpu_architecture]
}

run "no_extra_environment_by_default" {
  command = plan

  assert {
    condition     = alltrue([for e in values(output.task_environment) : !contains(keys(e), "SSL_CERT_FILE")])
    error_message = "Without extra_environment, no container gets any setting beyond the module's own."
  }
}

run "extra_environment_reaches_every_container_and_nothing_else" {
  command = plan

  variables {
    extra_environment = { SSL_CERT_FILE = "/etc/ssl/certs/emulator-ca.pem", AWS_ENDPOINT_URL = "https://floci:4566" }
  }

  assert {
    condition = alltrue([for t in concat(values(aws_ecs_task_definition.this), [aws_ecs_task_definition.migrate, aws_ecs_task_definition.seed]) :
      contains(jsondecode(t.container_definitions)[0].environment, { name = "SSL_CERT_FILE", value = "/etc/ssl/certs/emulator-ca.pem" }) &&
      contains(jsondecode(t.container_definitions)[0].environment, { name = "AWS_ENDPOINT_URL", value = "https://floci:4566" })
    ])
    error_message = "extra_environment must reach the environment of every container: the four services, the migration and the seed task."
  }

  assert {
    condition = alltrue([for k in ["api", "worker-general", "worker-runs", "beat", "migrate", "seed"] :
      output.task_environment[k].SSL_CERT_FILE == "/etc/ssl/certs/emulator-ca.pem"
    ])
    error_message = "The task_environment output must show the extra variables, as the containers get them."
  }

  assert {
    condition = alltrue([for t in concat(values(aws_ecs_task_definition.this), [aws_ecs_task_definition.migrate, aws_ecs_task_definition.seed]) :
      !anytrue([for s in jsondecode(t.container_definitions)[0].secrets : contains(["SSL_CERT_FILE", "AWS_ENDPOINT_URL"], s.name)])
    ])
    error_message = "Extra variables are plain settings: they must never become secrets."
  }

  assert {
    condition     = { for k, e in output.task_environment : k => { for name, value in e : name => value if !contains(["SSL_CERT_FILE", "AWS_ENDPOINT_URL"], name) } } == run.no_extra_environment_by_default.task_environment
    error_message = "Extra variables must only add to the module's settings, leaving every other setting as it was."
  }
}

run "rejects_extra_environment_that_overrides_a_module_setting" {
  command = plan

  variables {
    extra_environment = { REDIS_TLS = "false" }
  }

  expect_failures = [aws_ecs_task_definition.this]
}

run "rejects_an_extra_environment_name_that_is_not_a_variable_name" {
  command = plan

  variables {
    extra_environment = { "not a name" = "x" }
  }

  expect_failures = [var.extra_environment]
}

run "accepts_the_emulators_path_style_registry" {
  command = plan

  variables {
    image_repository_url = "localhost:4566/000000000000/eu-west-2/rag-agent-studio/api"
  }

  assert {
    condition     = alltrue([for t in values(aws_ecs_task_definition.this) : jsondecode(t.container_definitions)[0].image == "localhost:4566/000000000000/eu-west-2/rag-agent-studio/api:0123abc"])
    error_message = "The services must run the image from the emulator's path-style registry when given one (23-01)."
  }
}

run "rejects_a_localhost_registry_without_account_and_region" {
  command = plan

  variables {
    image_repository_url = "localhost:4566/rag-agent-studio/api"
  }

  expect_failures = [var.image_repository_url]
}

run "rejects_a_path_style_registry_on_another_host" {
  command = plan

  variables {
    image_repository_url = "registry.example.com:4566/000000000000/eu-west-2/rag-agent-studio/api"
  }

  expect_failures = [var.image_repository_url]
}
