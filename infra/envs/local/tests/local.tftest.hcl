# The local environment (ticket 23-03) composes the demo's modules for the rehearsal on the Floci emulator, and differs
# only in the inputs that work around the emulator's gaps. The AWS provider is mocked with the values Floci gives
# (ticket 23-01): nothing here calls AWS or the emulator.
mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "000000000000"
    }
  }

  mock_data "aws_region" {
    defaults = {
      region = "eu-west-2"
    }
  }

  # The managed prefix list catalogue the rehearsal gives the emulator (infra/rehearsal/prefix-lists.json).
  mock_data "aws_ec2_managed_prefix_list" {
    defaults = {
      entries = [{ cidr = "127.0.0.0/8", description = "" }, { cidr = "172.29.0.0/16", description = "" }]
    }
  }

  # Floci's path-style registry (FLOCI_SERVICES_ECR_URI_STYLE=path).
  mock_resource "aws_ecr_repository" {
    defaults = {
      arn            = "arn:aws:ecr:eu-west-2:000000000000:repository/rag-agent-studio/api"
      repository_url = "localhost:4566/000000000000/eu-west-2/rag-agent-studio/api"
    }
  }

  mock_resource "aws_secretsmanager_secret" {
    defaults = {
      arn = "arn:aws:secretsmanager:eu-west-2:000000000000:secret:studio-local/mocked-AbCdEf"
    }
  }

  mock_resource "aws_s3_bucket" {
    defaults = {
      arn                         = "arn:aws:s3:::studio-local-documents-000000000000"
      bucket_regional_domain_name = "studio-local-static-000000000000.s3.eu-west-2.amazonaws.com"
    }
  }

  mock_resource "aws_iam_role" {
    defaults = {
      arn = "arn:aws:iam::000000000000:role/studio-local-ecs-mocked"
    }
  }

  mock_resource "aws_appautoscaling_policy" {
    defaults = {
      arn = "arn:aws:autoscaling:eu-west-2:000000000000:scalingPolicy:00000000-0000-0000-0000-000000000000:resource/ecs/service/studio-local-ecs/mocked:policyName/mocked"
    }
  }

  # Floci names the load balancer <name>-<16 hex>.elb.<FLOCI_HOSTNAME>.
  mock_resource "aws_lb" {
    defaults = {
      arn      = "arn:aws:elasticloadbalancing:eu-west-2:000000000000:loadbalancer/app/studio-local-ecs/0123456789abcdef"
      dns_name = "studio-local-ecs-0123456789abcdef.elb.floci"
    }
  }

  mock_resource "aws_lb_target_group" {
    defaults = {
      arn = "arn:aws:elasticloadbalancing:eu-west-2:000000000000:targetgroup/studio-local-ecs-api/0123456789abcdef"
    }
  }

  mock_resource "aws_lb_listener" {
    defaults = {
      arn = "arn:aws:elasticloadbalancing:eu-west-2:000000000000:listener/app/studio-local-ecs/0123456789abcdef/0123456789abcdef"
    }
  }

  # FLOCI_SERVICES_CLOUDFRONT_DOMAIN_SUFFIX=cloudfront.localhost.
  mock_resource "aws_cloudfront_distribution" {
    defaults = {
      arn            = "arn:aws:cloudfront::000000000000:distribution/E2EXAMPLE0ABCD"
      domain_name    = "e2example0abcd.cloudfront.localhost"
      hosted_zone_id = "Z2FDTNDATAQYW2"
    }
  }

  mock_resource "aws_cloudfront_function" {
    defaults = {
      arn = "arn:aws:cloudfront::000000000000:function/studio-local-cdn-spa-fallback"
    }
  }

  # Left unset, the rotation period and the maintenance window are the service's to pick: these stand for its choice.
  mock_resource "aws_kms_key" {
    defaults = {
      arn                     = "arn:aws:kms:eu-west-2:000000000000:key/11111111-2222-3333-4444-555555555555"
      rotation_period_in_days = 0
    }
  }

  mock_resource "aws_elasticache_replication_group" {
    defaults = {
      maintenance_window = "service-picked"
    }
  }
}

override_resource {
  target = module.queue.aws_sqs_queue.this["general"]
  values = {
    arn = "arn:aws:sqs:eu-west-2:000000000000:studio-local-queue-general"
    url = "https://floci:4566/000000000000/studio-local-queue-general"
  }
}

override_resource {
  target = module.queue.aws_sqs_queue.this["runs"]
  values = {
    arn = "arn:aws:sqs:eu-west-2:000000000000:studio-local-queue-runs"
    url = "https://floci:4566/000000000000/studio-local-queue-runs"
  }
}

run "names_everything_like_the_demo_with_the_local_prefix" {
  command = apply

  assert {
    condition = output.module_names == {
      cache    = "studio-local-cache"
      cdn      = "studio-local-cdn"
      database = "studio-local-database"
      ecr      = "studio-local-ecr"
      ecs      = "studio-local-ecs"
      kms      = "studio-local-kms"
      network  = "studio-local-network"
      queue    = "studio-local-queue"
      storage  = "studio-local-storage"
    }
    error_message = "Every module must be named with the studio-local prefix."
  }

  assert {
    condition     = output.tags == { Environment = "local", Project = "rag-agent-studio" } && alltrue([for e in values(module.ecs.task_environment) : e.ENVIRONMENT == "local"])
    error_message = "The environment must be tagged local, and the app told it runs in local."
  }

  assert {
    condition     = output.ecr_repository_urls["rag-agent-studio/api"] == "localhost:4566/000000000000/eu-west-2/rag-agent-studio/api"
    error_message = "The registry deploy.sh pushes to must come from the ecr module's URLs: the emulator's path-style ones."
  }
}

run "works_around_the_emulators_gaps_through_inputs" {
  command = apply

  assert {
    condition     = module.network.nat_mode == "managed"
    error_message = "local must use the managed NAT gateway: the emulator cannot set the fck-nat interface's source/destination check."
  }

  assert {
    condition     = module.database.port == 7001 && alltrue([for e in values(module.ecs.task_environment) : e.DATABASE_PORT == "7001"])
    error_message = "local must ask for database port 7001, the first the emulator gives, and tell every container."
  }

  assert {
    condition     = alltrue([for e in values(module.ecs.task_environment) : e.DATABASE_TLS == "false" && e.REDIS_TLS == "true"])
    error_message = "The emulator's database serves no TLS, but the cache keeps TLS (and its auth token)."
  }

  assert {
    condition     = module.kms.rotation_period_in_days == { credentials = 0, data = 0 } && module.cache.maintenance_window == "service-picked"
    error_message = "local must leave the KMS rotation period and the cache maintenance window unset, as the emulator stores neither."
  }

  assert {
    condition     = module.cdn.api_origin_domain == "localhost"
    error_message = "The emulated distribution must send the API's paths to localhost, where the emulator serves the load balancer."
  }

  assert {
    condition = alltrue([for e in values(module.ecs.task_environment) : (
      e.SSL_CERT_FILE == "/etc/ssl/certs/ca-certificates.crt" && e.AWS_CA_BUNDLE == e.SSL_CERT_FILE && e.REQUESTS_CA_BUNDLE == e.SSL_CERT_FILE
    )])
    error_message = "Every container must be pointed at the image's CA bundle, which holds the emulator's CA."
  }

  assert {
    condition     = strcontains(module.ecs.task_environment.api.TRUSTED_PROXIES, "127.0.0.0/8") && strcontains(module.ecs.task_environment.api.TRUSTED_PROXIES, "172.29.0.0/16")
    error_message = "The API must trust the origin-facing ranges the rehearsal supplies to the emulator (loopback and its Docker network)."
  }
}

run "fits_a_16_gb_laptop" {
  command = apply

  assert {
    condition = { for k, t in module.ecs.service_tasks : k => { cpu = t.cpu, memory = t.memory } } == {
      api              = { cpu = 512, memory = 3072 }
      "worker-general" = { cpu = 1024, memory = 3072 }
      "worker-runs"    = { cpu = 1024, memory = 3072 }
      beat             = { cpu = 256, memory = 1024 }
    }
    error_message = "local must run each worker pool at 1 vCPU / 3 GB and the API at 3 GB (ticket 23-01's measurements), and Beat at 1 GB (23-03's)."
  }

  assert {
    condition     = contains(module.ecs.service_tasks["worker-general"].command, "--concurrency=1") && contains(module.ecs.service_tasks["worker-runs"].command, "--concurrency=1")
    error_message = "Each worker task must run one job at a time."
  }
}

run "runs_tasks_on_the_machines_architecture" {
  command = apply

  assert {
    condition     = module.ecs.cpu_architecture == "X86_64"
    error_message = "local must run X86_64 tasks by default (Intel machines)."
  }
}

run "runs_arm64_tasks_on_an_arm64_machine" {
  command = apply

  variables {
    cpu_architecture = "ARM64"
  }

  assert {
    condition     = module.ecs.cpu_architecture == "ARM64"
    error_message = "cpu_architecture = ARM64 (Apple silicon) must reach every task definition."
  }
}

run "outputs_the_emulated_distributions_address_for_the_smoke_check" {
  command = apply

  assert {
    condition     = output.cloudfront_url == "http://e2example0abcd.cloudfront.localhost:4566" && output.deploy.cloudfront_url == output.cloudfront_url
    error_message = "deploy.sh must smoke-check the distribution where the emulator serves it: plain HTTP on its port."
  }

  assert {
    condition = (
      output.deploy.cluster_name == module.ecs.cluster_name && output.deploy.services == module.ecs.service_names &&
      output.deploy.migration_task == module.ecs.migration_task && output.deploy.seed_task == module.ecs.seed_task &&
      output.deploy.static_bucket_name == module.storage.static_bucket_name && output.deploy.cloudfront_distribution_id == module.cdn.distribution_id
    )
    error_message = "The deploy output must hold everything deploy.sh and seed.sh read, as the demo's does."
  }
}

run "rejects_an_environment_other_than_local" {
  command = plan

  variables {
    environment = "demo"
  }

  expect_failures = [var.environment]
}

run "rejects_an_unknown_architecture" {
  command = plan

  variables {
    cpu_architecture = "amd64"
  }

  expect_failures = [var.cpu_architecture]
}

# Ticket 23-04: the rehearsal is a usable Studio.
run "the_emulated_distribution_is_the_studio_and_the_uploads_origin" {
  command = apply

  assert {
    condition     = alltrue([for k in ["api", "worker-general", "worker-runs", "seed"] : module.ecs.task_environment[k].STUDIO_URL == output.cloudfront_url])
    error_message = "Links in emails must point at the emulated distribution's address."
  }

  assert {
    condition     = module.storage.documents_cors_allowed_origin == "http://e2example0abcd.cloudfront.localhost:4566"
    error_message = "Browsers upload Documents from the emulated distribution's origin, so it must be the uploads CORS origin."
  }

  assert {
    condition     = module.ecs.task_environment.api.OBJECT_STORE_PUBLIC_ENDPOINT_URL == "http://localhost:4566" && !contains(keys(module.ecs.task_environment.seed), "OBJECT_STORE_PUBLIC_ENDPOINT_URL")
    error_message = "The API's presigned upload links must name an address the browser reaches (Floci's published port); the seed task, which uploads from inside the network, must keep the tasks' own endpoint."
  }
}

run "adds_no_custom_error_response" {
  command = apply

  assert {
    condition     = module.cdn.custom_error_responses == []
    error_message = "A distribution-wide 404-to-index response would replace the API's 404s too (ticket 23-04: Floci applies it to every origin, as AWS does), so local adds none."
  }
}
