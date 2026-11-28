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
    queue    = module.queue.name
    storage  = module.storage.name
  }
}

output "tags" {
  description = "Tags shared by every module in the environment."
  value       = local.tags
}

output "ecr_repository_urls" {
  description = "The emulator's repository URLs (localhost:<port>/<account>/<region>/<name>), keyed by repository name. deploy.sh pushes the images here."
  value       = module.ecr.repository_urls
}

output "bedrock_trust_principal" {
  description = "API task role ARN: the principal an Organisation trusts, with its external ID, in a Bedrock role."
  value       = module.ecs.api_task_role_arn
}

output "cloudfront_url" {
  description = "The emulated distribution's address: plain HTTP on Floci's port, on its *.cloudfront.localhost name. deploy.sh prints it and smoke-checks it."
  value       = local.url
}

output "cloudfront_distribution_id" {
  description = "Distribution ID the deploy workflow invalidates after uploading static assets."
  value       = module.cdn.distribution_id
}

output "static_bucket_name" {
  description = "Bucket the deploy workflow uploads the Studio and widget builds to."
  value       = module.storage.static_bucket_name
}

output "deploy" {
  description = "Everything scripts/deploy/deploy.sh reads after an apply (through scripts/deploy/rehearse.sh): the cluster, services and their new task definitions, the migration task, the static bucket and the distribution. scripts/deploy/seed.sh reads the seed task from it (ticket 10-05), and scripts/deploy/scale.sh the cluster, services and job queues (ticket 22-07)."
  value = {
    image_tag                  = var.image_tag
    cluster_name               = module.ecs.cluster_name
    services                   = module.ecs.service_names
    task_definition_arns       = module.ecs.task_definition_arns
    migration_task             = module.ecs.migration_task
    seed_task                  = module.ecs.seed_task
    queue_names                = { for k, q in module.queue.queues : k => q.name }
    static_bucket_name         = module.storage.static_bucket_name
    cloudfront_distribution_id = module.cdn.distribution_id
    cloudfront_url             = local.url
  }
}

output "jobs_metric_namespace" {
  description = "Namespace of the Jobs metric (waiting plus in-flight jobs, by QueueName) the worker pools' alarms watch here; `make rehearse-scale` publishes it (ticket 23-05)."
  value       = module.ecs.jobs_metric_namespace
}
