variable "environment" {
  description = "Short-lived environment name. Only demo exists (plan section 2)."
  type        = string
  default     = "demo"

  validation {
    condition     = contains(["demo"], var.environment)
    error_message = "environment must be demo."
  }
}

variable "aws_region" {
  description = "AWS region for the demo environment. Matches the AWS_REGION default in the CI workflows."
  type        = string
  default     = "eu-west-2"

  validation {
    condition     = can(regex("^[a-z]{2}(-[a-z]+)+-[0-9]$", var.aws_region))
    error_message = "aws_region must be an AWS region name such as eu-west-2."
  }
}

variable "image_tag" {
  description = "Backend image tag the services run. The deploy workflow (ticket 09-06) sets it to the pushed git SHA; until then services point at a tag that does not exist yet."
  type        = string
  default     = "bootstrap"
}
