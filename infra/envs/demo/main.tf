# Demo environment (stub, ticket 01-02). Spec 09 adds the AWS provider, the S3 state backend and real resources.
locals {
  name_prefix = "studio-${var.environment}"
  tags        = { Environment = var.environment, Project = "rag-agent-studio" }
}

module "network" {
  source      = "../../modules/network"
  name_prefix = local.name_prefix
  tags        = local.tags
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
