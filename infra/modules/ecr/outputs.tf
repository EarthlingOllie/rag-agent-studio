output "name" {
  description = "Name the module gives its resources."
  value       = local.name
}

output "tags" {
  description = "Tags the module applies to its resources."
  value       = local.tags
}

output "repository_urls" {
  description = "Repository URL of each repository, keyed by name. The ecs module runs images from the API one."
  value       = { for name, r in aws_ecr_repository.this : name => r.repository_url }
}

output "repository_arns" {
  description = "ARN of each repository, keyed by name. Task execution roles may pull only from these."
  value       = { for name, r in aws_ecr_repository.this : name => r.arn }
}
