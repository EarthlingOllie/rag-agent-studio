variable "aws_region" {
  description = "Region for the state bucket, its key and every environment."
  type        = string
  default     = "eu-west-2"
}

variable "name_prefix" {
  description = "Prefix for the bootstrap's own resources: the state bucket, its key alias and the deploy role."
  type        = string
  default     = "rag-agent-studio"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,22}[a-z0-9]$", var.name_prefix))
    error_message = "name_prefix must be 3-24 characters of lowercase letters, digits and hyphens, starting with a letter."
  }
}

variable "github_repository" {
  description = "The GitHub repository, as owner/name, whose workflows may assume the deploy role."
  type        = string
  default     = "EarthlingOllie/rag-agent-studio"
}

variable "existing_oidc_provider_arn" {
  description = "ARN of a GitHub OIDC provider the account already has, or null to create one."
  type        = string
  default     = null
}

variable "deploy_managed_policy_arns" {
  description = "Managed policies for the deploy role. PowerUserAccess covers every service except IAM."
  type        = list(string)
  default     = ["arn:aws:iam::aws:policy/PowerUserAccess"]
}

variable "managed_resource_prefix" {
  description = "Name prefix of the IAM roles and policies environments create (environments use studio-<env>)."
  type        = string
  default     = "studio-"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]*-$", var.managed_resource_prefix)) && !startswith("${var.name_prefix}-github-deploy", var.managed_resource_prefix)
    error_message = "managed_resource_prefix must end with a hyphen and must not match the deploy role's own name."
  }
}
