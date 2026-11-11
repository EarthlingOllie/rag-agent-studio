output "name" {
  description = "Name the module gives its resources."
  value       = local.name
}

output "tags" {
  description = "Tags the module applies to its resources."
  value       = local.tags
}

output "credentials_key_arn" {
  description = "ARN of the key that wraps Provider Credential data keys (ADR-0006). Grant it to the API task role only."
  value       = aws_kms_key.this["credentials"].arn
}

output "credentials_key_alias" {
  description = "Alias of the Provider Credentials key, for the API's KMS_KEY_ID setting."
  value       = aws_kms_alias.this["credentials"].name
}

output "data_key_arn" {
  description = "ARN of the key that encrypts data at rest in RDS, ElastiCache, the Documents bucket and the platform secrets."
  value       = aws_kms_key.this["data"].arn
}
