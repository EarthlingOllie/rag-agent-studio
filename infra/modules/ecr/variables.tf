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

variable "repository_names" {
  description = "ECR repositories to create, for example rag-agent-studio/api (the API, worker and Beat image). Names match the deploy workflow's push targets."
  type        = set(string)

  validation {
    condition     = length(var.repository_names) > 0 && alltrue([for n in var.repository_names : can(regex("^[a-z0-9]+([._-][a-z0-9]+)*(/[a-z0-9]+([._-][a-z0-9]+)*)*$", n)) && length(n) <= 256])
    error_message = "repository_names must hold at least one ECR repository name: lowercase letters, digits, and . _ - / separators."
  }
}

variable "kms_key_arn" {
  description = "KMS key that encrypts the images at rest (the kms module's data key)."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:kms:[a-z0-9-]+:[0-9]{12}:key/", var.kms_key_arn))
    error_message = "kms_key_arn must be a KMS key ARN."
  }
}

variable "keep_tagged_images" {
  description = "How many of the newest tagged images each repository keeps. Older ones expire."
  type        = number
  default     = 20

  validation {
    condition     = var.keep_tagged_images >= 1 && floor(var.keep_tagged_images) == var.keep_tagged_images
    error_message = "keep_tagged_images must be a positive whole number."
  }
}

variable "untagged_expiry_days" {
  description = "Days after which untagged images (superseded layers and failed pushes) expire."
  type        = number
  default     = 7

  validation {
    condition     = var.untagged_expiry_days >= 1 && floor(var.untagged_expiry_days) == var.untagged_expiry_days
    error_message = "untagged_expiry_days must be a positive whole number."
  }
}

variable "force_delete" {
  description = "Delete repositories even when they still hold images. On for the demo, so one destroy run removes everything."
  type        = bool
  default     = false
}
