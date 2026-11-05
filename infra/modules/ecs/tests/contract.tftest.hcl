# Module contract for the ecs module (ticket 09-04), at the module seam, with a mocked AWS provider.
# Runs that compare resource IDs or ARNs use `command = apply`: the mock provider only invents them at apply
# time, and it never calls AWS, so apply here creates nothing real.
mock_provider "aws" {
  mock_data "aws_region" {
    defaults = {
      region = "eu-west-2"
    }
  }

  mock_data "aws_ec2_managed_prefix_list" {
    defaults = {
      id = "pl-93a247fa"
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

  mock_resource "aws_cloudwatch_log_group" {
    defaults = {
      arn = "arn:aws:logs:eu-west-2:123456789012:log-group:/ecs/studio-demo-ecs/mocked"
    }
  }
}

variables {
  name_prefix          = "studio-demo"
  tags                 = { Environment = "demo", Project = "rag-agent-studio" }
  vpc_id               = "vpc-0123456789abcdef0"
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
}

run "runs_api_worker_and_beat_on_arm64_fargate" {
  command = apply

  assert {
    condition     = keys(aws_ecs_service.this) == ["api", "beat", "worker"]
    error_message = "There must be exactly three services: api, worker and beat."
  }

  assert {
    condition     = alltrue([for k, s in aws_ecs_service.this : s.cluster == aws_ecs_cluster.this.id && s.launch_type == "FARGATE" && s.task_definition == aws_ecs_task_definition.this[k].arn])
    error_message = "Each service must run its own task definition on Fargate in the module's cluster."
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
      api    = ["512", "1024"]
      worker = ["2048", "8192"]
      beat   = ["256", "512"]
    }
    error_message = "Task sizes must default to the spec 09 cost defaults (API 0.5 vCPU / 1 GB, worker 2 vCPU / 8 GB)."
  }

  assert {
    condition     = { for k, s in aws_ecs_service.this : k => s.desired_count } == { api = 1, worker = 1, beat = 1 }
    error_message = "Each service must run one task by default."
  }
}

run "task_sizes_and_counts_are_variables" {
  command = plan

  variables {
    task_sizes = {
      api    = { cpu = 1024, memory = 2048 }
      worker = { cpu = 4096, memory = 16384 }
      beat   = { cpu = 256, memory = 1024 }
    }
    desired_counts = { api = 2, worker = 3, beat = 0 }
  }

  assert {
    condition = { for k, t in aws_ecs_task_definition.this : k => [t.cpu, t.memory] } == {
      api    = ["1024", "2048"]
      worker = ["4096", "16384"]
      beat   = ["256", "1024"]
    }
    error_message = "task_sizes must reach each task definition."
  }

  assert {
    condition     = { for k, s in aws_ecs_service.this : k => s.desired_count } == { api = 2, worker = 3, beat = 0 }
    error_message = "desired_counts must reach each service."
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
      api    = ["python", "-m", "app.serve"]
      worker = ["celery", "-A", "app.worker.main", "--quiet", "worker", "--loglevel=INFO", "--concurrency=2"]
      beat   = ["celery", "-A", "app.worker.main", "--quiet", "beat", "--loglevel=INFO", "--schedule=/tmp/celerybeat-schedule"]
    }
    error_message = "Each service must run its own command, as in docker-compose.yml (migrations run as a separate task)."
  }
}

run "each_service_has_its_own_least_privilege_task_role" {
  command = apply

  assert {
    condition     = alltrue([for k, t in aws_ecs_task_definition.this : t.task_role_arn == aws_iam_role.task[k].arn]) && { for k, r in aws_iam_role.task : k => r.name } == { api = "studio-demo-ecs-api-task", worker = "studio-demo-ecs-worker-task", beat = "studio-demo-ecs-beat-task" }
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
    condition     = keys(aws_iam_role_policy.task) == ["api", "worker"] && alltrue([for k, p in aws_iam_role_policy.task : p.role == aws_iam_role.task[k].id])
    error_message = "Beat calls no AWS API, so its task role must have no permissions at all."
  }

  assert {
    condition     = output.task_role_policies.beat == null
    error_message = "Beat's task role must have no policy document."
  }

  assert {
    condition     = output.task_role_policies.api == jsondecode(aws_iam_role_policy.task["api"].policy) && output.task_role_policies.worker == jsondecode(aws_iam_role_policy.task["worker"].policy)
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
      ]
    }
    error_message = "The API may use Document objects, the credentials key, and assume other accounts' roles only with an external ID."
  }
}

run "the_worker_reads_documents_and_never_touches_credentials" {
  command = plan

  assert {
    condition = output.task_role_policies.worker == {
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
      ]
    }
    error_message = "The worker may use Document objects only: no credentials key and no role assumption."
  }
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
      length(aws_ecs_service.this["worker"].load_balancer) == 0 && length(aws_ecs_service.this["beat"].load_balancer) == 0
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
    condition = { for k, t in aws_ecs_task_definition.this : k => jsondecode(t.container_definitions)[0].secrets } == {
      api = [
        { name = "DATABASE_PASSWORD", valueFrom = var.database.password_secret_arn },
        { name = "REDIS_AUTH_TOKEN", valueFrom = var.cache.auth_token_secret_arn },
        { name = "SESSION_SECRET", valueFrom = aws_secretsmanager_secret.platform["session"].arn },
      ]
      worker = [
        { name = "DATABASE_PASSWORD", valueFrom = var.database.password_secret_arn },
        { name = "REDIS_AUTH_TOKEN", valueFrom = var.cache.auth_token_secret_arn },
      ]
      beat = [
        { name = "REDIS_AUTH_TOKEN", valueFrom = var.cache.auth_token_secret_arn },
      ]
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
    condition = { for e in jsondecode(aws_ecs_task_definition.this["api"].container_definitions)[0].environment : e.name => e.value } == {
      ENVIRONMENT             = "demo"
      AWS_REGION              = "eu-west-2"
      DATABASE_HOST           = "studio-demo-database.abc.eu-west-2.rds.amazonaws.com"
      DATABASE_PORT           = "5432"
      DATABASE_NAME           = "studio"
      DATABASE_USER           = "studio"
      REDIS_HOST              = "master.studio-demo-cache.abc.euw2.cache.amazonaws.com"
      REDIS_PORT              = "6379"
      REDIS_TLS               = "true"
      DOCUMENTS_BUCKET        = "studio-demo-documents-123456789012"
      CREDENTIALS_KMS_KEY_ARN = "arn:aws:kms:eu-west-2:123456789012:key/11111111-1111-1111-1111-111111111111"
    }
    error_message = "The API must get its connection settings as plain environment variables."
  }

  assert {
    condition = (
      !contains([for e in jsondecode(aws_ecs_task_definition.this["worker"].container_definitions)[0].environment : e.name], "CREDENTIALS_KMS_KEY_ARN") &&
      contains([for e in jsondecode(aws_ecs_task_definition.this["worker"].container_definitions)[0].environment : e.name], "DOCUMENTS_BUCKET") &&
      !contains([for e in jsondecode(aws_ecs_task_definition.this["beat"].container_definitions)[0].environment : e.name], "DOCUMENTS_BUCKET") &&
      !contains([for e in jsondecode(aws_ecs_task_definition.this["beat"].container_definitions)[0].environment : e.name], "DATABASE_HOST")
    )
    error_message = "Only the API learns the credentials key, and Beat learns nothing about the database or Documents."
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
    condition     = { for k, g in aws_cloudwatch_log_group.service : k => [g.name, g.retention_in_days] } == { api = ["/ecs/studio-demo-ecs/api", 14], worker = ["/ecs/studio-demo-ecs/worker", 14], beat = ["/ecs/studio-demo-ecs/beat", 14] }
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
      { for k, r in aws_iam_role.execution : k => r.name } == { api = "studio-demo-ecs-api-execution", worker = "studio-demo-ecs-worker-execution", beat = "studio-demo-ecs-beat-execution" } &&
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
          Resource = ["arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo-cache/auth-token-BBBBBB"]
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
    error_message = "Beat's execution role may pull the image, write its own logs and read only the Redis token."
  }

  assert {
    condition = output.execution_role_policies.api.Statement[3].Resource == [
      "arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo-database/master-password-AAAAAA",
      "arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo-cache/auth-token-BBBBBB",
      aws_secretsmanager_secret.platform["session"].arn,
    ]
    error_message = "The API's execution role may read exactly the database password, Redis token and session secret."
  }

  assert {
    condition = output.execution_role_policies.worker.Statement[3].Resource == [
      "arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo-database/master-password-AAAAAA",
      "arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo-cache/auth-token-BBBBBB",
    ]
    error_message = "The worker's execution role may read exactly the database password and Redis token."
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
      "api-https"       = [aws_security_group.service["api"].id, "tcp", 443, 443, "0.0.0.0/0", null]
      "api-postgres"    = [aws_security_group.service["api"].id, "tcp", 5432, 5432, null, "sg-0database00000001"]
      "api-redis"       = [aws_security_group.service["api"].id, "tcp", 6379, 6379, null, "sg-0cache00000000001"]
      "worker-https"    = [aws_security_group.service["worker"].id, "tcp", 443, 443, "0.0.0.0/0", null]
      "worker-postgres" = [aws_security_group.service["worker"].id, "tcp", 5432, 5432, null, "sg-0database00000001"]
      "worker-redis"    = [aws_security_group.service["worker"].id, "tcp", 6379, 6379, null, "sg-0cache00000000001"]
      "beat-https"      = [aws_security_group.service["beat"].id, "tcp", 443, 443, "0.0.0.0/0", null]
      "beat-redis"      = [aws_security_group.service["beat"].id, "tcp", 6379, 6379, null, "sg-0cache00000000001"]
    })
    error_message = "Services may reach HTTPS (AWS APIs and model providers), and only the data stores they use."
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
    condition     = alltrue([for k in ["api", "worker"] : aws_ecs_service.this[k].deployment_maximum_percent == 200 && aws_ecs_service.this[k].deployment_minimum_healthy_percent == 100])
    error_message = "API and worker deployments must start new tasks before stopping old ones."
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
    condition     = output.service_names == { api = "studio-demo-ecs-api", worker = "studio-demo-ecs-worker", beat = "studio-demo-ecs-beat" }
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
      api    = { cpu = 512, memory = 512 }
      worker = { cpu = 2048, memory = 8192 }
      beat   = { cpu = 256, memory = 512 }
    }
  }

  expect_failures = [var.task_sizes]
}

run "rejects_an_unknown_cpu_value" {
  command = plan

  variables {
    task_sizes = {
      api    = { cpu = 300, memory = 1024 }
      worker = { cpu = 2048, memory = 8192 }
      beat   = { cpu = 256, memory = 512 }
    }
  }

  expect_failures = [var.task_sizes]
}

run "accepts_every_fargate_cpu_size" {
  command = plan

  variables {
    task_sizes = {
      api    = { cpu = 1024, memory = 8192 }
      worker = { cpu = 16384, memory = 122880 }
      beat   = { cpu = 8192, memory = 61440 }
    }
  }

  assert {
    condition     = aws_ecs_task_definition.this["worker"].cpu == "16384" && aws_ecs_task_definition.this["beat"].memory == "61440"
    error_message = "The largest Fargate sizes must be accepted."
  }
}

run "accepts_4_vcpu_tasks" {
  command = plan

  variables {
    task_sizes = {
      api    = { cpu = 4096, memory = 30720 }
      worker = { cpu = 2048, memory = 16384 }
      beat   = { cpu = 256, memory = 2048 }
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
      api    = { cpu = 512, memory = 1024 }
      worker = { cpu = 2048, memory = 8192 }
    }
  }

  expect_failures = [var.task_sizes]
}

run "rejects_two_beats" {
  command = plan

  variables {
    desired_counts = { api = 1, worker = 1, beat = 2 }
  }

  expect_failures = [var.desired_counts]
}

run "rejects_a_negative_count" {
  command = plan

  variables {
    desired_counts = { api = -1, worker = 1, beat = 1 }
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
