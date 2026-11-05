# The demo environment wires every module with one shared prefix and tag set. CI access (ci-oidc) belongs to infra/bootstrap.
# The network module creates AWS resources, so the AWS provider is mocked: nothing here calls AWS.
mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "123456789012"
    }
  }

  # Real-looking key ARNs, so the data modules' input validation runs against a mocked apply.
  mock_data "aws_region" {
    defaults = {
      region = "eu-west-2"
    }
  }

  # Real-looking ARNs and URLs, so the compute module's input validation and policies run against a mocked apply.
  mock_resource "aws_ecr_repository" {
    defaults = {
      arn            = "arn:aws:ecr:eu-west-2:123456789012:repository/rag-agent-studio/api"
      repository_url = "123456789012.dkr.ecr.eu-west-2.amazonaws.com/rag-agent-studio/api"
    }
  }

  mock_resource "aws_secretsmanager_secret" {
    defaults = {
      arn = "arn:aws:secretsmanager:eu-west-2:123456789012:secret:studio-demo/mocked-AbCdEf"
    }
  }

  mock_resource "aws_s3_bucket" {
    defaults = {
      arn = "arn:aws:s3:::studio-demo-documents-123456789012"
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

  mock_resource "aws_kms_key" {
    defaults = {
      arn = "arn:aws:kms:eu-west-2:123456789012:key/11111111-2222-3333-4444-555555555555"
    }
  }
}

run "wires_every_module_with_the_environment_prefix" {
  command = plan

  assert {
    condition = output.module_names == {
      cache    = "studio-demo-cache"
      cdn      = "studio-demo-cdn"
      database = "studio-demo-database"
      ecr      = "studio-demo-ecr"
      ecs      = "studio-demo-ecs"
      kms      = "studio-demo-kms"
      network  = "studio-demo-network"
      storage  = "studio-demo-storage"
    }
    error_message = "Every module must be named from the demo prefix."
  }

  assert {
    condition     = output.tags == { Environment = "demo", Project = "rag-agent-studio" }
    error_message = "The environment's tags must carry the environment and project."
  }

  assert {
    condition     = module.network.nat_mode == "fck-nat"
    error_message = "The demo environment must egress through fck-nat (ADR-0010)."
  }

  assert {
    condition     = module.network.availability_zones == tolist(["eu-west-2a", "eu-west-2b"])
    error_message = "The demo VPC must span two AZs of its region."
  }
}

run "wires_the_data_modules_into_the_environment" {
  command = apply

  assert {
    condition     = module.storage.documents_bucket_name == "studio-demo-documents-123456789012" && module.storage.static_bucket_name == "studio-demo-static-123456789012"
    error_message = "The demo buckets must be named from the demo prefix and the account."
  }

  assert {
    condition     = module.storage.documents_cors_allowed_origin == null
    error_message = "Until the cdn module exists, the Documents bucket must allow no cross-origin requests."
  }

  assert {
    condition     = module.kms.credentials_key_alias == "alias/studio-demo-kms-credentials"
    error_message = "The demo's Provider Credentials key must be named from the demo prefix."
  }

  assert {
    condition     = module.database.port == 5432 && module.cache.port == 6379
    error_message = "The database and cache must be wired into the environment."
  }
}

run "wires_the_compute_module_into_the_data_modules" {
  command = apply

  assert {
    condition     = keys(module.ecr.repository_urls) == ["rag-agent-studio/api", "rag-agent-studio/studio"]
    error_message = "The demo must have the two repositories the deploy workflow pushes to."
  }

  assert {
    condition     = output.ecr_repository_urls == module.ecr.repository_urls
    error_message = "The environment must output the ECR repository URLs (spec 09 outputs)."
  }

  assert {
    condition     = output.bedrock_trust_principal == module.ecs.api_task_role_arn
    error_message = "The environment must output the API task role ARN as the Bedrock trust principal (spec 09 outputs)."
  }

  assert {
    condition     = { for k, r in module.database.admitted_client_security_group_ids : k => r } == { api = module.ecs.service_security_group_ids["api"], worker = module.ecs.service_security_group_ids["worker"] }
    error_message = "Only the API and worker may connect to the database."
  }

  assert {
    condition     = module.cache.admitted_client_security_group_ids == module.ecs.service_security_group_ids
    error_message = "The API, worker and Beat may connect to Redis."
  }

  assert {
    condition     = keys(module.ecs.service_names) == ["api", "beat", "worker"] && var.image_tag == "bootstrap"
    error_message = "The demo must run the three services, at the bootstrap tag until the deploy workflow sets one."
  }
}

run "rejects_an_unknown_environment" {
  command = plan

  variables {
    environment = "prod"
  }

  expect_failures = [var.environment]
}
