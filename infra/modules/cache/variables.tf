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

variable "vpc_id" {
  description = "VPC the database's security group belongs to."
  type        = string
}

variable "subnet_ids" {
  description = "Private subnets, in at least two AZs, for the cache subnet group. Never public subnets."
  type        = list(string)

  validation {
    condition     = length(distinct(var.subnet_ids)) >= 2
    error_message = "subnet_ids must name at least two different private subnets."
  }
}

variable "kms_key_arn" {
  description = "KMS key that encrypts Redis data, snapshots and the auth token secret (the kms module's data key)."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:kms:[a-z0-9-]+:[0-9]{12}:key/", var.kms_key_arn))
    error_message = "kms_key_arn must be a KMS key ARN."
  }
}

variable "client_security_group_ids" {
  description = "Security groups allowed to connect on the Redis port, keyed by a static client name (for example api, worker, beat)."
  type        = map(string)
  default     = {}
}

variable "engine_version" {
  description = "Redis engine version. Must be Redis 7, the first with TLS-required mode and the version Celery is tested on locally."
  type        = string
  default     = "7.1"

  validation {
    condition     = can(regex("^7\\.[0-9]+$", var.engine_version))
    error_message = "engine_version must be Redis 7, for example 7.1."
  }
}

variable "node_type" {
  description = "ElastiCache node type. cache.t4g.micro keeps the demo cheap."
  type        = string
  default     = "cache.t4g.micro"

  validation {
    condition     = startswith(var.node_type, "cache.")
    error_message = "node_type must be an ElastiCache node type such as cache.t4g.micro."
  }
}

variable "replicas" {
  description = "Read replicas next to the primary. 0 for the demo's single node; 1 or more also turns on automatic failover across AZs."
  type        = number
  default     = 0

  validation {
    condition     = var.replicas >= 0 && var.replicas <= 5 && floor(var.replicas) == var.replicas
    error_message = "replicas must be a whole number from 0 to 5."
  }
}

variable "snapshot_retention_days" {
  description = "Days of daily snapshots to keep. Redis holds the broker queue and rate-limit counters, so 1 day is enough for the demo."
  type        = number
  default     = 1

  validation {
    condition     = var.snapshot_retention_days >= 1 && var.snapshot_retention_days <= 35
    error_message = "snapshot_retention_days must be between 1 and 35."
  }
}

variable "auth_token_version" {
  description = "Bump to generate a new Redis auth token and write it to both ElastiCache and Secrets Manager."
  type        = number
  default     = 1

  validation {
    condition     = var.auth_token_version >= 1 && floor(var.auth_token_version) == var.auth_token_version
    error_message = "auth_token_version must be a positive whole number."
  }
}
