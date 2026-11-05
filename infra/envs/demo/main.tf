# Demo environment (ticket 01-02 stub; ticket 09-02 adds the AWS provider and the real network module;
# ticket 09-03 adds the real database, cache, storage and kms modules).
# Spec 09 adds the S3 state backend and the remaining real resources.
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

# Client security groups (api, worker, beat) are added by the ecs module (ticket 09-04). Until then nothing
# can connect to the database or cache.
module "database" {
  source      = "../../modules/database"
  name_prefix = local.name_prefix
  tags        = local.tags
  vpc_id      = module.network.vpc_id
  subnet_ids  = module.network.private_subnet_ids
  kms_key_arn = module.kms.data_key_arn
}

module "cache" {
  source      = "../../modules/cache"
  name_prefix = local.name_prefix
  tags        = local.tags
  vpc_id      = module.network.vpc_id
  subnet_ids  = module.network.private_subnet_ids
  kms_key_arn = module.kms.data_key_arn
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

module "ecs" {
  source      = "../../modules/ecs"
  name_prefix = local.name_prefix
  tags        = local.tags
}

module "cdn" {
  source      = "../../modules/cdn"
  name_prefix = local.name_prefix
  tags        = local.tags
}

module "ci_oidc" {
  source      = "../../modules/ci-oidc"
  name_prefix = local.name_prefix
  tags        = local.tags
}
