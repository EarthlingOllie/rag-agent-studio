output "name" {
  description = "Name the module gives its resources."
  value       = local.name
}

output "tags" {
  description = "Tags the module applies to its resources."
  value       = local.tags
}

output "role_arn" {
  description = "ARN of the deploy role. Store it as the AWS_DEPLOY_ROLE_ARN repository secret."
  value       = aws_iam_role.deploy.arn
}

output "role_name" {
  description = "Name of the deploy role."
  value       = aws_iam_role.deploy.name
}

output "oidc_provider_arn" {
  description = "ARN of the GitHub OIDC provider the role trusts."
  value       = local.oidc_provider_arn
}

output "trust_policy" {
  description = "The deploy role's trust policy, as an object."
  value       = local.trust_policy
}
