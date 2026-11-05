variable "name_prefix" {
  description = "Prefix for every resource name, for example studio-demo. Lowercase letters, digits and hyphens."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,22}[a-z0-9]$", var.name_prefix))
    error_message = "name_prefix must be 3-24 characters of lowercase letters, digits and hyphens, starting with a letter."
  }
}

variable "tags" {
  description = "Tags applied to every resource the module creates."
  type        = map(string)
  default     = {}
}

variable "github_repository" {
  description = "The one GitHub repository, as owner/name, whose workflows may assume the deploy role."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}$", var.github_repository))
    error_message = "github_repository must be a literal owner/name with no wildcards."
  }
}

variable "subject_claims" {
  description = "Token subjects within the repository that may assume the role: branch refs, pull_request, or environments."
  type        = list(string)
  default     = ["ref:refs/heads/*", "pull_request", "environment:*"]

  validation {
    condition = length(var.subject_claims) > 0 && alltrue([
      for claim in var.subject_claims : can(regex("^(ref:refs/(heads|tags)/[A-Za-z0-9._/*-]+|pull_request|environment:[A-Za-z0-9._*-]+)$", claim))
    ])
    error_message = "subject_claims must be ref:refs/heads/..., ref:refs/tags/..., pull_request or environment:... entries."
  }
}

variable "existing_oidc_provider_arn" {
  description = "ARN of a GitHub OIDC provider already in the account. Null creates one (an account can hold only one per URL)."
  type        = string
  default     = null
}

variable "managed_policy_arns" {
  description = "Managed policy ARNs attached to the deploy role."
  type        = list(string)
  default     = []
}

variable "inline_policy_json" {
  description = "Inline policy document (JSON) for the deploy role, or null for none."
  type        = string
  default     = null
}
