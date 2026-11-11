output "name" {
  description = "Name the module gives its resources."
  value       = local.name
}

output "tags" {
  description = "Tags the module applies to its resources."
  value       = local.tags
}

output "address" {
  description = "Hostname of the database, reachable only from inside the VPC."
  value       = aws_db_instance.this.address
}

output "port" {
  description = "Postgres port."
  value       = aws_db_instance.this.port
}

output "database_name" {
  description = "Name of the application database."
  value       = aws_db_instance.this.db_name
}

output "master_username" {
  description = "Master user name."
  value       = aws_db_instance.this.username
}

output "password_secret_arn" {
  description = "Secrets Manager secret holding the master password, for injection into ECS tasks."
  value       = aws_secretsmanager_secret.master_password.arn
}

output "security_group_id" {
  description = "Security group on the database."
  value       = aws_security_group.this.id
}

output "admitted_client_security_group_ids" {
  description = "Client security groups admitted on the Postgres port, keyed by client name, as the ingress rules record them."
  value       = { for k, r in aws_vpc_security_group_ingress_rule.clients : k => r.referenced_security_group_id }
}
