output "name" {
  description = "Name the module gives its resources."
  value       = local.name
}

output "tags" {
  description = "Tags the module applies to its resources."
  value       = local.tags
}

output "distribution_id" {
  description = "ID of the distribution, for the deploy workflow's invalidations."
  value       = aws_cloudfront_distribution.this.id
}

output "distribution_arn" {
  description = "ARN of the distribution: the only principal the static bucket lets read assets."
  value       = aws_cloudfront_distribution.this.arn
}

output "domain_name" {
  description = "Domain the distribution answers on: the custom domain if set, otherwise its *.cloudfront.net name."
  value       = local.custom_domain ? var.domain_name : aws_cloudfront_distribution.this.domain_name
}

output "url" {
  description = "Public HTTPS origin of the Studio, widget and API, with no trailing slash. The Documents bucket's CORS rule allows only this origin."
  value       = "https://${local.custom_domain ? var.domain_name : aws_cloudfront_distribution.this.domain_name}"
}

output "certificate_arn" {
  description = "ACM certificate of the custom domain, or null without one."
  value       = local.custom_domain ? aws_acm_certificate.this[0].arn : null
}

output "api_origin_domain" {
  description = "Origin of /api/* and /widget/a/*: the ALB's DNS name."
  value       = var.alb_dns_name
}
