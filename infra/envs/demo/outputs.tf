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

output "cloudfront_url" {
  description = "Public HTTPS URL of the Studio, widget and API. The deploy workflow prints it and smoke-checks it."
  value       = module.cdn.url
}

output "cloudfront_distribution_id" {
  description = "Distribution ID the deploy workflow invalidates after uploading static assets."
  value       = module.cdn.distribution_id
}

output "static_bucket_name" {
  description = "Bucket the deploy workflow uploads the Studio and widget builds to."
  value       = module.storage.static_bucket_name
}
