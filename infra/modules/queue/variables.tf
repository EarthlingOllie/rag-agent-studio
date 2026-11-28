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

variable "general_visibility_timeout_seconds" {
  description = "Seconds a received message on the general queue stays hidden from other workers. Long enough for a normal ingestion, Re-embed or deletion."
  type        = number
  default     = 3600

  validation {
    condition     = var.general_visibility_timeout_seconds >= 0 && var.general_visibility_timeout_seconds <= 43200 && floor(var.general_visibility_timeout_seconds) == var.general_visibility_timeout_seconds
    error_message = "general_visibility_timeout_seconds must be a whole number of seconds from 0 to 43200 (the SQS maximum)."
  }
}

variable "runs_visibility_timeout_seconds" {
  description = "Seconds a received message on the runs queue stays hidden from other workers. Twelve hours, the SQS maximum, for long Evaluation Runs and Suggestion runs."
  type        = number
  default     = 43200

  validation {
    condition     = var.runs_visibility_timeout_seconds >= 0 && var.runs_visibility_timeout_seconds <= 43200 && floor(var.runs_visibility_timeout_seconds) == var.runs_visibility_timeout_seconds
    error_message = "runs_visibility_timeout_seconds must be a whole number of seconds from 0 to 43200 (the SQS maximum)."
  }
}

variable "max_receive_count" {
  description = "Redrive limit: deliveries of one message before it is moved to its dead-letter queue."
  type        = number
  default     = 5

  validation {
    condition     = var.max_receive_count >= 1 && var.max_receive_count <= 1000 && floor(var.max_receive_count) == var.max_receive_count
    error_message = "max_receive_count must be a whole number from 1 to 1000."
  }
}

variable "message_retention_seconds" {
  description = "Seconds a job message waits on the general or runs queue before SQS drops it. The database still records the job (ADR-0020)."
  type        = number
  default     = 345600 # 4 days, the SQS default.

  validation {
    condition     = var.message_retention_seconds >= 60 && var.message_retention_seconds <= 1209600 && floor(var.message_retention_seconds) == var.message_retention_seconds
    error_message = "message_retention_seconds must be a whole number of seconds from 60 to 1209600 (14 days)."
  }
}
