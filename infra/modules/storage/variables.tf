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

variable "kms_key_arn" {
  description = "KMS key that encrypts Documents at rest (the kms module's data key)."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:kms:[a-z0-9-]+:[0-9]{12}:key/", var.kms_key_arn))
    error_message = "kms_key_arn must be a KMS key ARN."
  }
}

variable "force_destroy" {
  description = "Let terraform destroy delete buckets that still hold objects. On for the throwaway demo only."
  type        = bool
  default     = false
}

variable "documents_cors_allowed_origin" {
  description = "The CloudFront origin (https://<distribution>.cloudfront.net, or the custom domain) that browsers upload Documents from with presigned URLs. Null means no cross-origin access at all. The demo passes the cdn module's url."
  type        = string
  default     = null

  validation {
    condition     = var.documents_cors_allowed_origin == null || can(regex("^https://[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$", var.documents_cors_allowed_origin))
    error_message = "documents_cors_allowed_origin must be a single https:// origin with no wildcard, port or path."
  }
}

variable "static_assets_distribution_arn" {
  description = "ARN of the CloudFront distribution allowed to read static assets through origin access control. Null means no one can read them. The demo passes the cdn module's distribution."
  type        = string
  default     = null

  validation {
    condition     = var.static_assets_distribution_arn == null || can(regex("^arn:aws[a-z-]*:cloudfront::[0-9]{12}:distribution/[A-Z0-9]+$", var.static_assets_distribution_arn))
    error_message = "static_assets_distribution_arn must be a CloudFront distribution ARN."
  }
}
