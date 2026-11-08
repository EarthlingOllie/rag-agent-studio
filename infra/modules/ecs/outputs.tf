output "name" {
  description = "Name the module gives its resources."
  value       = local.name
}

output "tags" {
  description = "Tags the module applies to its resources."
  value       = local.tags
}

output "task_role_policies" {
  description = "Policy document of each service's task role, keyed by service (null: no permissions)."
  value       = local.task_role_policies
}

output "alb_dns_name" {
  description = "DNS name of the ALB: the cdn module's origin for /api/* and /widget/a/*."
  value       = aws_lb.this.dns_name
}

output "origin_header_name" {
  description = "Header CloudFront must add to every origin request to the ALB."
  value       = var.origin_header_name
}

output "origin_header_value" {
  description = "Secret value of that header. The ALB answers 403 to any request without it."
  value       = terraform_data.origin_secret.output
  sensitive   = true
}

output "execution_role_policies" {
  description = "Policy document of each service's execution role, keyed by service."
  value       = local.execution_role_policies
}

output "service_security_group_ids" {
  description = "Security group of each service's tasks, keyed by service: the database and cache admit these."
  value       = { for k, sg in aws_security_group.service : k => sg.id }
}

output "cluster_name" {
  description = "Name of the ECS cluster."
  value       = aws_ecs_cluster.this.name
}

output "service_names" {
  description = "ECS service name of each service, keyed by service."
  value       = { for k, s in aws_ecs_service.this : k => s.name }
}

output "task_role_arns" {
  description = "Task role ARN of each service, keyed by service."
  value       = { for k, r in aws_iam_role.task : k => r.arn }
}

output "api_task_role_arn" {
  description = "The API task role: the principal customers trust, with their external ID, in Bedrock roles (spec 02)."
  value       = aws_iam_role.task["api"].arn
}

output "log_group_names" {
  description = "CloudWatch log group of each service, keyed by service."
  value       = { for k, g in aws_cloudwatch_log_group.service : k => g.name }
}

output "task_definition_arns" {
  description = "Task definition ARN of each service at the current image tag, keyed by service. The deploy workflow rolls each service onto it after migrations succeed."
  value       = { for k, t in aws_ecs_task_definition.this : k => t.arn }
}

output "migration_task" {
  description = "How the deploy workflow runs the one-off migration task: task definition, container, private subnets and security group."
  value = {
    task_definition_arn = aws_ecs_task_definition.migrate.arn
    container_name      = "migrate"
    subnet_ids          = var.private_subnet_ids
    security_group_id   = aws_security_group.migrate.id
  }
}

output "migration_security_group_id" {
  description = "Security group of the migration task: the database admits it."
  value       = aws_security_group.migrate.id
}

output "migration_task_role_policy" {
  description = "Policy document of the migration task role (null: no permissions)."
  value       = null
}

output "migration_execution_role_policy" {
  description = "Policy document of the migration task's execution role."
  value       = local.migration_execution_role_policy
}

output "seed_task" {
  description = "How the seed workflow runs the one-off seed task (ticket 10-05): task definition, container, private subnets, security group, and the log group and stream prefix it prints the output from."
  value = {
    task_definition_arn = aws_ecs_task_definition.seed.arn
    container_name      = "seed"
    subnet_ids          = var.private_subnet_ids
    security_group_id   = aws_security_group.seed.id
    log_group_name      = aws_cloudwatch_log_group.seed.name
    log_stream_prefix   = "seed"
  }
}

output "seed_security_group_id" {
  description = "Security group of the seed task: the database and the cache admit it."
  value       = aws_security_group.seed.id
}

output "seed_task_role_policy" {
  description = "Policy document of the seed task role."
  value       = local.seed_task_role_policy
}

output "seed_execution_role_policy" {
  description = "Policy document of the seed task's execution role."
  value       = local.seed_execution_role_policy
}

output "task_environment" {
  description = "Plain environment variables of each container (api, worker, beat, migrate, seed), keyed by name. Secrets are not included: they are injected by reference to Secrets Manager."
  value       = merge(local.environment, { migrate = local.migrate_environment, seed = local.seed_environment })
}
