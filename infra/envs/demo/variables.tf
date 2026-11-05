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

variable "domain_name" {
  description = "Optional custom domain for the demo, for example studio.example.com. Null serves on the distribution's *.cloudfront.net domain; a name adds an ACM certificate and Route 53 records (spec 09 story 20)."
  type        = string
  default     = null
}

variable "hosted_zone_name" {
  description = "Public Route 53 hosted zone holding domain_name's records. Null means a zone named exactly domain_name."
  type        = string
  default     = null
}
