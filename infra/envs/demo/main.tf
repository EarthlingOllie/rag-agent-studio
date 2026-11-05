# Demo environment (ticket 01-02 stub; ticket 09-02 adds the AWS provider and the real network module).
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

module "database" {
  source      = "../../modules/database"
  name_prefix = local.name_prefix
  tags        = local.tags
}

module "cache" {
  source      = "../../modules/cache"
  name_prefix = local.name_prefix
  tags        = local.tags
}

module "storage" {
  source      = "../../modules/storage"
  name_prefix = local.name_prefix
  tags        = local.tags
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
