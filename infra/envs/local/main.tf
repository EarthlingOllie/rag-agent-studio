# The local environment: the demo's composition, rehearsed on the Floci emulator with no AWS account (spec 23, ticket
# 23-03). It composes the same modules as envs/demo and differs only in inputs and provider settings; each input that
# differs works around an emulator gap that ticket 23-01 found, and says which. No module branches on "is this local"
# (spec 23 story 30). scripts/deploy/rehearse.sh applies it, through the unchanged scripts/deploy/deploy.sh.
locals {
  name_prefix = "studio-${var.environment}"
  tags        = { Environment = var.environment, Project = "rag-agent-studio" }

  # Floci serves the distribution over plain HTTP on its own port, on the *.cloudfront.localhost name it gives it
  # (23-01, research finding 12); the cdn module's url is the https:// address AWS would serve.
  url = "http://${module.cdn.distribution_domain_name}:${var.emulator_port}"
}

# Every service the modules use is pinned to the emulator, so this environment never reaches AWS whatever credentials
# the machine holds; the dummy credentials come from the environment (the wrapper sets them). The emulator serves
# buckets by path, and has no credentials or instance metadata to check.
provider "aws" {
  region                      = var.aws_region
  s3_use_path_style           = true
  skip_credentials_validation = true
  skip_metadata_api_check     = true

  endpoints {
    acm                    = var.emulator_endpoint
    applicationautoscaling = var.emulator_endpoint
    cloudfront             = var.emulator_endpoint
    cloudwatch             = var.emulator_endpoint
    ec2                    = var.emulator_endpoint
    ecr                    = var.emulator_endpoint
    ecs                    = var.emulator_endpoint
    elasticache            = var.emulator_endpoint
    elbv2                  = var.emulator_endpoint
    iam                    = var.emulator_endpoint
    kms                    = var.emulator_endpoint
    logs                   = var.emulator_endpoint
    rds                    = var.emulator_endpoint
    route53                = var.emulator_endpoint
    s3                     = var.emulator_endpoint
    s3control              = var.emulator_endpoint
    secretsmanager         = var.emulator_endpoint
    sqs                    = var.emulator_endpoint
    sts                    = var.emulator_endpoint
  }

  # No default_tags, unlike the demo: every module tags its own resources (ManagedBy included), and default tags would
  # reach the SPA fallback function, whose tags Floci drops on create (ticket 23-04).
}

module "network" {
  source             = "../../modules/network"
  name_prefix        = local.name_prefix
  tags               = local.tags
  availability_zones = ["${var.aws_region}a", "${var.aws_region}b"]
  # The emulator cannot turn off the fck-nat interface's source/destination check (23-01, blocker 9).
  managed_nat = true
}

module "database" {
  source      = "../../modules/database"
  name_prefix = local.name_prefix
  tags        = local.tags
  vpc_id      = module.network.vpc_id
  subnet_ids  = module.network.private_subnet_ids
  kms_key_arn = module.kms.data_key_arn
  # The emulator puts the database on a port from 7001 and reads any other back differently (23-01, drift).
  port = 7001
  client_security_group_ids = merge(
    { for k in ["api", "worker-general", "worker-runs"] : k => module.ecs.service_security_group_ids[k] },
    { migrate = module.ecs.migration_security_group_id, seed = module.ecs.seed_security_group_id },
  )
}

module "cache" {
  source      = "../../modules/cache"
  name_prefix = local.name_prefix
  tags        = local.tags
  vpc_id      = module.network.vpc_id
  subnet_ids  = module.network.private_subnet_ids
  kms_key_arn = module.kms.data_key_arn
  # The emulator does not store a maintenance window (23-01, drift).
  maintenance_window = null
  client_security_group_ids = merge(
    { for k in ["api", "worker-general", "worker-runs", "beat"] : k => module.ecs.service_security_group_ids[k] },
    { seed = module.ecs.seed_security_group_id },
  )
}

module "queue" {
  source      = "../../modules/queue"
  name_prefix = local.name_prefix
  tags        = local.tags
}

module "storage" {
  source                         = "../../modules/storage"
  name_prefix                    = local.name_prefix
  tags                           = local.tags
  kms_key_arn                    = module.kms.data_key_arn
  force_destroy                  = true      # make rehearse-down destroys everything in one run.
  documents_cors_allowed_origin  = local.url # Browsers upload from the emulated distribution's origin (ticket 23-04).
  static_assets_distribution_arn = module.cdn.distribution_arn
}

module "kms" {
  source      = "../../modules/kms"
  name_prefix = local.name_prefix
  tags        = local.tags
  # The emulator reads a key's rotation period back as 0 (23-01, drift); automatic rotation stays on.
  rotation_period_in_days = null
}

module "ecr" {
  source           = "../../modules/ecr"
  name_prefix      = local.name_prefix
  tags             = local.tags
  repository_names = ["rag-agent-studio/api", "rag-agent-studio/studio"]
  kms_key_arn      = module.kms.data_key_arn
  force_delete     = true # make rehearse-down destroys everything in one run.
}

module "ecs" {
  source               = "../../modules/ecs"
  name_prefix          = local.name_prefix
  tags                 = local.tags
  vpc_id               = module.network.vpc_id
  vpc_cidr             = module.network.vpc_cidr
  public_subnet_ids    = module.network.public_subnet_ids
  private_subnet_ids   = module.network.private_subnet_ids
  image_repository_url = module.ecr.repository_urls["rag-agent-studio/api"]
  image_repository_arn = module.ecr.repository_arns["rag-agent-studio/api"]
  image_tag            = var.image_tag
  documents_bucket_arn = module.storage.documents_bucket_arn
  credentials_key_arn  = module.kms.credentials_key_arn
  data_key_arn         = module.kms.data_key_arn
  studio_url           = local.url # Links in emails point at the emulated distribution (ticket 23-04).
  demo_pages           = true

  # The emulator runs each task as a container on this machine and refuses an image of another architecture
  # (23-01, blocker 2).
  cpu_architecture = var.cpu_architecture

  # The emulator gives its tasks no CA bundle (23-01, blocker 7): the rehearsal's image carries one with Floci's root
  # CA in it, and every client library is pointed at it, so the cache's TLS and the HTTPS queue URLs verify.
  # Python's ssl module and redis read SSL_CERT_FILE, boto3 AWS_CA_BUNDLE, and httpx and requests REQUESTS_CA_BUNDLE.
  extra_environment = {
    SSL_CERT_FILE      = var.ca_bundle_path
    AWS_CA_BUNDLE      = var.ca_bundle_path
    REQUESTS_CA_BUNDLE = var.ca_bundle_path
  }
  # The API's presigned upload links name Floci's published port, which the browser reaches. Only the API: the seed
  # task uploads from inside the network, at the endpoint Floci gives every task (ticket 23-04).
  api_extra_environment = {
    OBJECT_STORE_PUBLIC_ENDPOINT_URL = "http://localhost:${var.emulator_port}"
  }

  # Sizes that fit a 16 GB laptop, from 23-01's measurements: one job per worker task at 1 vCPU / 3 GB (one process
  # peaks at about 2.3 GB), and the API at 3 GB, above the 2.33 GB its local models take. The emulator enforces task
  # memory as a hard limit. Beat gets 1 GB: it took 451 of its 512 MiB in the first rehearsal (ticket 23-03).
  task_sizes = {
    api              = { cpu = 512, memory = 3072 }
    "worker-general" = { cpu = 1024, memory = 3072 }
    "worker-runs"    = { cpu = 1024, memory = 3072 }
    beat             = { cpu = 256, memory = 1024 }
  }
  # A laptop's share of the demo's scaling (ticket 23-05): at most 2 API tasks (new ones stay well under their 3 GB
  # until a Visitor message loads the models), 2 general tasks and 1 runs task at once, about 13 GB with all of them
  # busy; and short cooldowns and idle times, so `make rehearse-scale` shows each service out and back in minutes.
  scaling = {
    api            = { max = 2, scale_out_cooldown = 30, scale_in_cooldown = 60 }
    worker-general = { max = 2, jobs_per_task = 1, scale_out_cooldown = 30, scale_in_cooldown = 30, idle_minutes = 1 }
    worker-runs    = { max = 1, jobs_per_task = 1, scale_out_cooldown = 30, scale_in_cooldown = 30, idle_minutes = 1 }
  }
  # The emulator never evaluates the metric math the pools' alarms use (23-01), nor runs a step policy on an alarm
  # state set by hand (23-05): the alarms watch one published metric per queue, Rehearsal/SQS Jobs (waiting plus in
  # flight), which `make rehearse-scale` publishes (scripts/deploy/rehearsal/drive-scaling.sh).
  jobs_metric_namespace = "Rehearsal/SQS"

  database = {
    address             = module.database.address
    port                = module.database.port
    name                = module.database.database_name
    username            = module.database.master_username
    password_secret_arn = module.database.password_secret_arn
    security_group_id   = module.database.security_group_id
    # The emulator's database is a plain pgvector container and serves no TLS (23-01, data-plane.log: ssl off).
    tls = false
  }

  cache = {
    address               = module.cache.primary_endpoint_address
    port                  = module.cache.port
    auth_token_secret_arn = module.cache.auth_token_secret_arn
    security_group_id     = module.cache.security_group_id
  }

  queues = module.queue.queues
}

module "cdn" {
  source                             = "../../modules/cdn"
  name_prefix                        = local.name_prefix
  tags                               = local.tags
  static_bucket_regional_domain_name = module.storage.static_bucket_regional_domain_name
  static_origin_access_control_id    = module.storage.static_origin_access_control_id
  alb_dns_name                       = module.ecs.alb_dns_name
  # The emulator refuses the load balancer's name as an origin; it serves the load balancer on localhost inside its
  # own container, which FLOCI_SERVICES_CLOUDFRONT_ALLOWED_PRIVATE_ORIGIN_HOSTS admits (23-01, blocker 5).
  api_origin_domain = "localhost"
  # The emulator drops the tags the provider sends when it creates a CloudFront Function, so the plan after a fresh
  # apply would show them changing (ticket 23-04): the SPA fallback function is left untagged. It stores the function
  # without running it (23-01, finding 11), so the rehearsal's front end (infra/rehearsal/front) runs the same file in
  # front of it; no 404-to-index error response, which would also replace the API's own 404s (ticket 23-04).
  function_tags       = false
  origin_header_name  = module.ecs.origin_header_name
  origin_header_value = module.ecs.origin_header_value
}
