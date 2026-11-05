# Demo environment (ticket 01-02 stub; ticket 09-02 adds the AWS provider and the real network module;
# ticket 09-03 adds the real database, cache, storage and kms modules; ticket 09-04 adds ecr and the real ecs module).
# Spec 09 adds the remaining real resources. State is in S3 (backend.tf).
# The GitHub OIDC deploy role is not here: infra/bootstrap creates it once, before this environment can be planned.
locals {
  name_prefix = "studio-${var.environment}"
  tags        = { Environment = var.environment, Project = "rag-agent-studio" }
}

# Credentials come from the environment (GitHub OIDC in CI). default_tags backs up each module's own tags.
provider "aws" {
  region = var.aws_region

  default_tags {
    tags = merge(local.tags, { ManagedBy = "terraform" })
  }
}

module "network" {
  source             = "../../modules/network"
  name_prefix        = local.name_prefix
  tags               = local.tags
  availability_zones = ["${var.aws_region}a", "${var.aws_region}b"]
}

# Only the API and worker connect to Postgres; Beat only needs Redis.
module "database" {
  source                    = "../../modules/database"
  name_prefix               = local.name_prefix
  tags                      = local.tags
  vpc_id                    = module.network.vpc_id
  subnet_ids                = module.network.private_subnet_ids
  kms_key_arn               = module.kms.data_key_arn
  client_security_group_ids = { for k in ["api", "worker"] : k => module.ecs.service_security_group_ids[k] }
}

module "cache" {
  source                    = "../../modules/cache"
  name_prefix               = local.name_prefix
  tags                      = local.tags
  vpc_id                    = module.network.vpc_id
  subnet_ids                = module.network.private_subnet_ids
  kms_key_arn               = module.kms.data_key_arn
  client_security_group_ids = { for k in ["api", "worker", "beat"] : k => module.ecs.service_security_group_ids[k] }
}

# The cdn module (ticket 09-05) supplies the CloudFront origin for Documents CORS and the distribution
# allowed to read static assets. Until then neither is allowed.
module "storage" {
  source        = "../../modules/storage"
  name_prefix   = local.name_prefix
  tags          = local.tags
  kms_key_arn   = module.kms.data_key_arn
  force_destroy = true # The demo is torn down with one destroy run (spec 09 story 27).
}

module "kms" {
  source      = "../../modules/kms"
  name_prefix = local.name_prefix
  tags        = local.tags
}

# The deploy workflow pushes rag-agent-studio/api (API, worker and Beat) and rag-agent-studio/studio.
module "ecr" {
  source           = "../../modules/ecr"
  name_prefix      = local.name_prefix
  tags             = local.tags
  repository_names = ["rag-agent-studio/api", "rag-agent-studio/studio"]
  kms_key_arn      = module.kms.data_key_arn
  force_delete     = true # The demo is torn down with one destroy run (spec 09 story 27).
}

# The cdn module (ticket 09-05) reads origin_header_name and origin_header_value and points /api/* and
# /widget/a/* at alb_dns_name.
module "ecs" {
  source               = "../../modules/ecs"
  name_prefix          = local.name_prefix
  tags                 = local.tags
  vpc_id               = module.network.vpc_id
  public_subnet_ids    = module.network.public_subnet_ids
  private_subnet_ids   = module.network.private_subnet_ids
  image_repository_url = module.ecr.repository_urls["rag-agent-studio/api"]
  image_repository_arn = module.ecr.repository_arns["rag-agent-studio/api"]
  image_tag            = var.image_tag
  documents_bucket_arn = module.storage.documents_bucket_arn
  credentials_key_arn  = module.kms.credentials_key_arn
  data_key_arn         = module.kms.data_key_arn

  database = {
    address             = module.database.address
    port                = module.database.port
    name                = module.database.database_name
    username            = module.database.master_username
    password_secret_arn = module.database.password_secret_arn
    security_group_id   = module.database.security_group_id
  }

  cache = {
    address               = module.cache.primary_endpoint_address
    port                  = module.cache.port
    auth_token_secret_arn = module.cache.auth_token_secret_arn
    security_group_id     = module.cache.security_group_id
  }
}

module "cdn" {
  source      = "../../modules/cdn"
  name_prefix = local.name_prefix
  tags        = local.tags
}
