variable "name_prefix" {
  description = "Prefix for every resource name, for example studio-demo. Lowercase letters, digits and hyphens."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,22}[a-z0-9]$", var.name_prefix))
    error_message = "name_prefix must be 3-24 characters of lowercase letters, digits and hyphens, starting with a letter."
  }
}

variable "tags" {
  description = "Standard tags applied to every resource the module creates. Must include Project and Environment."
  type        = map(string)

  validation {
    condition     = alltrue([for key in ["Project", "Environment"] : contains(keys(var.tags), key)])
    error_message = "tags must include Project and Environment."
  }
}

variable "static_bucket_regional_domain_name" {
  description = "Regional domain of the static assets bucket (the storage module's output): the origin for /, /embed.js and /widget/assets/*."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9.-]+\\.s3\\.[a-z0-9-]+\\.amazonaws\\.com$", var.static_bucket_regional_domain_name))
    error_message = "static_bucket_regional_domain_name must be an S3 bucket regional domain such as my-bucket.s3.eu-west-2.amazonaws.com."
  }
}

variable "static_origin_access_control_id" {
  description = "Origin access control that signs CloudFront's requests to the static bucket (the storage module's output)."
  type        = string

  validation {
    condition     = length(var.static_origin_access_control_id) > 0
    error_message = "static_origin_access_control_id must not be empty."
  }
}

variable "alb_dns_name" {
  description = "DNS name of the ALB (the ecs module's output): the origin for /api/* and /widget/a/*."
  type        = string

  validation {
    condition     = can(regex("^[a-zA-Z0-9.-]+\\.elb\\.amazonaws\\.com$", var.alb_dns_name))
    error_message = "alb_dns_name must be an ALB DNS name ending in .elb.amazonaws.com."
  }
}

variable "origin_header_name" {
  description = "Header CloudFront adds to every request to the ALB (the ecs module's output)."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9-]+$", var.origin_header_name))
    error_message = "origin_header_name must be an HTTP header name: letters, digits and hyphens."
  }
}

variable "origin_header_value" {
  description = "Secret value of that header (the ecs module's output). The ALB answers 403 without it."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.origin_header_value) >= 32
    error_message = "origin_header_value must be at least 32 characters."
  }
}

variable "origin_read_timeout" {
  description = "Seconds CloudFront waits for each response packet from the ALB. SSE needs it long: the API sends a heartbeat inside it. Above 60 needs an AWS quota increase."
  type        = number
  default     = 60

  validation {
    condition     = var.origin_read_timeout >= 30 && var.origin_read_timeout <= 180
    error_message = "origin_read_timeout must be 30-180 seconds, the range CloudFront allows."
  }
}

variable "domain_name" {
  description = "Optional custom domain, for example studio.example.com. Null (the default) serves on the distribution's *.cloudfront.net domain (ADR-0011); a name adds an ACM certificate and Route 53 records."
  type        = string
  default     = null

  validation {
    condition     = var.domain_name == null || can(regex("^([a-z0-9]([a-z0-9-]*[a-z0-9])?\\.)+[a-z]{2,63}$", var.domain_name))
    error_message = "domain_name must be a lowercase hostname such as studio.example.com, with no scheme, port or path."
  }
}

variable "hosted_zone_name" {
  description = "Public Route 53 hosted zone that holds domain_name's records, for example example.com. Null means a zone named exactly domain_name."
  type        = string
  default     = null

  validation {
    condition     = var.hosted_zone_name == null || var.domain_name != null
    error_message = "hosted_zone_name needs domain_name."
  }
}
