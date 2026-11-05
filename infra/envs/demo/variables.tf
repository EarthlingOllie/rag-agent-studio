variable "environment" {
  description = "Short-lived environment name. Only demo exists (plan section 2)."
  type        = string
  default     = "demo"

  validation {
    condition     = contains(["demo"], var.environment)
    error_message = "environment must be demo."
  }
}
