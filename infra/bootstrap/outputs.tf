output "state_bucket_name" {
  description = "State bucket. Store it as the TF_STATE_BUCKET repository variable."
  value       = aws_s3_bucket.state.bucket
}

output "backend_config" {
  description = "Settings for the S3 backend of every environment (terraform init -backend-config=...)."
  value = {
    bucket       = aws_s3_bucket.state.bucket
    region       = var.aws_region
    use_lockfile = true
  }
}

output "deploy_role_arn" {
  description = "Deploy role. Store it as the AWS_DEPLOY_ROLE_ARN repository secret."
  value       = module.ci_oidc.role_arn
}

output "deploy_trust_policy" {
  description = "The deploy role's trust policy."
  value       = module.ci_oidc.trust_policy
}

output "deploy_policy" {
  description = "The deploy role's inline policy."
  value       = local.deploy_policy
}
