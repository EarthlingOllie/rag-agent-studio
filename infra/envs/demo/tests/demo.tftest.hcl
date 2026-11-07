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
      arn                         = "arn:aws:s3:::studio-demo-documents-123456789012"
      bucket_regional_domain_name = "studio-demo-static-123456789012.s3.eu-west-2.amazonaws.com"
    }
  }

  mock_resource "aws_iam_role" {
    defaults = {
      arn = "arn:aws:iam::123456789012:role/studio-demo-ecs-mocked"
    }
  }

  mock_resource "aws_lb" {
    defaults = {
      arn      = "arn:aws:elasticloadbalancing:eu-west-2:123456789012:loadbalancer/app/studio-demo-ecs/0123456789abcdef"
      dns_name = "studio-demo-ecs-1234567890.eu-west-2.elb.amazonaws.com"
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

  # Real-looking CloudFront values, so the storage module's CORS origin and bucket policy validation run.
  mock_resource "aws_cloudfront_distribution" {
    defaults = {
      arn            = "arn:aws:cloudfront::123456789012:distribution/E2EXAMPLE0ABCD"
      domain_name    = "d111111abcdef8.cloudfront.net"
      hosted_zone_id = "Z2FDTNDATAQYW2"
    }
  }

  mock_resource "aws_cloudfront_function" {
    defaults = {
      arn = "arn:aws:cloudfront::123456789012:function/studio-demo-cdn-spa-fallback"
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
    condition     = { for k, r in module.database.admitted_client_security_group_ids : k => r } == { api = module.ecs.service_security_group_ids["api"], worker = module.ecs.service_security_group_ids["worker"], migrate = module.ecs.migration_security_group_id }
    error_message = "Only the API, the worker and the migration task may connect to the database."
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

run "wires_the_cdn_in_front_of_the_static_bucket_and_the_alb" {
  command = apply

  assert {
    condition     = output.cloudfront_url == "https://d111111abcdef8.cloudfront.net" && output.cloudfront_url == module.cdn.url
    error_message = "The environment must output the CloudFront URL (spec 09 outputs), on its default domain."
  }

  assert {
    condition     = module.storage.documents_cors_allowed_origin == module.cdn.url
    error_message = "Browsers may upload Documents to S3 only from the CloudFront origin (spec 09 story 10)."
  }

  assert {
    condition     = module.storage.static_assets_distribution_arn == module.cdn.distribution_arn
    error_message = "Only this distribution may read static assets, through origin access control."
  }

  assert {
    condition     = module.cdn.api_origin_domain == module.ecs.alb_dns_name && module.ecs.alb_dns_name == "studio-demo-ecs-1234567890.eu-west-2.elb.amazonaws.com"
    error_message = "The cdn's API origin must be the compute module's ALB."
  }

  assert {
    condition     = output.cloudfront_distribution_id == module.cdn.distribution_id && module.cdn.certificate_arn == null
    error_message = "The demo has no custom domain by default, and outputs the distribution ID for the deploy workflow's invalidations."
  }
}

run "outputs_everything_the_deploy_workflow_needs" {
  command = apply

  variables {
    image_tag = "0123abc"
  }

  assert {
    condition = output.deploy == {
      image_tag                  = "0123abc"
      cluster_name               = "studio-demo-ecs"
      services                   = { api = "studio-demo-ecs-api", worker = "studio-demo-ecs-worker", beat = "studio-demo-ecs-beat" }
      task_definition_arns       = module.ecs.task_definition_arns
      migration_task             = module.ecs.migration_task
      static_bucket_name         = "studio-demo-static-123456789012"
      cloudfront_distribution_id = module.cdn.distribution_id
      cloudfront_url             = "https://d111111abcdef8.cloudfront.net"
    }
    error_message = "The deploy output must name the cluster, services, task definitions, migration task, static bucket and distribution."
  }

  assert {
    condition     = tolist(output.deploy.migration_task.subnet_ids) == tolist(module.network.private_subnet_ids) && output.deploy.migration_task.security_group_id == module.ecs.migration_security_group_id
    error_message = "The migration task must run in the private subnets with the security group the database admits."
  }

  assert {
    condition     = alltrue([for arn in values(output.deploy.task_definition_arns) : arn != null]) && keys(output.deploy.task_definition_arns) == ["api", "beat", "worker"]
    error_message = "The deploy output must carry a task definition for each service at the new tag."
  }
}

run "a_domain_name_adds_acm_and_route53_to_the_demo" {
  command = plan

  variables {
    domain_name = "studio.example.com"
  }

  assert {
    condition     = output.cloudfront_url == "https://studio.example.com"
    error_message = "With domain_name set, the environment must serve on that domain."
  }
}

run "rejects_an_unknown_environment" {
  command = plan

  variables {
    environment = "prod"
  }

  expect_failures = [var.environment]
}
