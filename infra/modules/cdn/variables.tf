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
