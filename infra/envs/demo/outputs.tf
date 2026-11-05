output "module_names" {
  description = "Resource name each module uses, keyed by module."
  value = {
    cache    = module.cache.name
    cdn      = module.cdn.name
    database = module.database.name
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
