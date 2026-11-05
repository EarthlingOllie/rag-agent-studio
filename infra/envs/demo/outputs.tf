output "module_names" {
  description = "Resource name each module uses, keyed by module."
  value = {
    cache    = module.cache.name
    cdn      = module.cdn.name
    database = module.database.name
    ecr      = module.ecr.name
    ecs      = module.ecs.name
    kms      = module.kms.name
    network  = module.network.name
    storage  = module.storage.name
  }
}

output "tags" {
  description = "Tags shared by every module in the environment."
  value       = local.tags
}

output "ecr_repository_urls" {
  description = "ECR repository URLs, keyed by repository name. The deploy workflow pushes images here."
  value       = module.ecr.repository_urls
}

output "bedrock_trust_principal" {
  description = "API task role ARN: the principal an Organisation trusts, with its external ID, in a Bedrock role."
  value       = module.ecs.api_task_role_arn
}
