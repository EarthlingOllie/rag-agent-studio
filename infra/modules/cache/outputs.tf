output "name" {
  description = "Name the module gives its resources."
  value       = local.name
}

output "tags" {
  description = "Tags the module applies to its resources."
  value       = local.tags
}

output "primary_endpoint_address" {
  description = "Hostname of the Redis primary, reachable only from inside the VPC. Connect with rediss:// (TLS)."
  value       = aws_elasticache_replication_group.this.primary_endpoint_address
}

output "port" {
  description = "Redis port."
  value       = aws_elasticache_replication_group.this.port
}

output "auth_token_secret_arn" {
  description = "Secrets Manager secret holding the Redis AUTH token, for injection into ECS tasks."
  value       = aws_secretsmanager_secret.auth_token.arn
}

output "security_group_id" {
  description = "Security group on the cache."
  value       = aws_security_group.this.id
}
