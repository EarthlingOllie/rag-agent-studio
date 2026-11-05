output "name" {
  description = "Name the module gives its resources."
  value       = local.name
}

output "tags" {
  description = "Tags the module applies to its resources."
  value       = local.tags
}

output "documents_cors_allowed_origin" {
  description = "The only origin allowed to make cross-origin requests to the Documents bucket, or null for none."
  value       = var.documents_cors_allowed_origin
}

output "static_origin_access_control_id" {
  description = "Origin access control the cdn module attaches to the static assets origin."
  value       = aws_cloudfront_origin_access_control.static.id
}

output "documents_bucket_name" {
  description = "Name of the Documents bucket, for the API's storage settings."
  value       = aws_s3_bucket.this["documents"].bucket
}

output "documents_bucket_arn" {
  description = "ARN of the Documents bucket, for the API and worker task role policies."
  value       = aws_s3_bucket.this["documents"].arn
}

output "static_bucket_name" {
  description = "Name of the static assets bucket, for the deploy workflow's upload."
  value       = aws_s3_bucket.this["static"].bucket
}

output "static_bucket_arn" {
  description = "ARN of the static assets bucket, for the deploy role's upload policy."
  value       = aws_s3_bucket.this["static"].arn
}

output "static_bucket_regional_domain_name" {
  description = "Regional domain of the static assets bucket, for the CloudFront origin."
  value       = aws_s3_bucket.this["static"].bucket_regional_domain_name
}

output "static_assets_distribution_arn" {
  description = "The only CloudFront distribution allowed to read static assets, or null for none."
  value       = var.static_assets_distribution_arn
}
