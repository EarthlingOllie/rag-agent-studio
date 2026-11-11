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
  description = "Private subnets, in at least two AZs, that the database may be placed in. Never public subnets."
  type        = list(string)

  validation {
    condition     = length(distinct(var.subnet_ids)) >= 2
    error_message = "subnet_ids must name at least two different private subnets (RDS requires two AZs)."
  }
}

variable "kms_key_arn" {
  description = "KMS key that encrypts the storage, backups and the password secret (the kms module's data key)."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:kms:[a-z0-9-]+:[0-9]{12}:key/", var.kms_key_arn))
    error_message = "kms_key_arn must be a KMS key ARN."
  }
}

variable "client_security_group_ids" {
  description = "Security groups allowed to connect on the Postgres port, keyed by a static client name (for example api, worker)."
  type        = map(string)
  default     = {}
}

variable "engine_version" {
  description = "Postgres engine version. Must be major version 16; a bare \"16\" takes the newest 16.x minor."
  type        = string
  default     = "16"

  validation {
    condition     = can(regex("^16(\\.[0-9]+)?$", var.engine_version))
    error_message = "engine_version must be Postgres 16, for example 16 or 16.6."
  }
}

variable "instance_class" {
  description = "RDS instance class. db.t4g.micro keeps the demo cheap."
  type        = string
  default     = "db.t4g.micro"

  validation {
    condition     = startswith(var.instance_class, "db.")
    error_message = "instance_class must be an RDS instance class such as db.t4g.micro."
  }
}

variable "allocated_storage_gb" {
  description = "Initial gp3 storage in GB. Storage autoscales up to max_allocated_storage_gb."
  type        = number
  default     = 20

  validation {
    condition     = var.allocated_storage_gb >= 20
    error_message = "allocated_storage_gb must be at least 20 (the gp3 minimum for Postgres)."
  }
}

variable "max_allocated_storage_gb" {
  description = "Ceiling for storage autoscaling in GB."
  type        = number
  default     = 100
}

variable "backup_retention_days" {
  description = "Days of automated backups (point-in-time recovery). AWS allows 1 to 35; 0 would turn backups off and is rejected."
  type        = number
  default     = 7

  validation {
    condition     = var.backup_retention_days >= 1 && var.backup_retention_days <= 35
    error_message = "backup_retention_days must be between 1 and 35, so backups are always on."
  }
}

variable "multi_az" {
  description = "Run a standby in a second AZ. Off for the demo (single-AZ, ADR-0010 cost defaults)."
  type        = bool
  default     = false
}

variable "deletion_protection" {
  description = "Block deletion of the instance. Off for the demo so it can be destroyed in one run."
  type        = bool
  default     = false
}

variable "final_snapshot" {
  description = "Take a final snapshot when the instance is destroyed. Off for the throwaway demo."
  type        = bool
  default     = false
}

variable "database_name" {
  description = "Name of the application database created on the instance."
  type        = string
  default     = "studio"

  validation {
    condition     = can(regex("^[a-z][a-z0-9_]{0,62}$", var.database_name))
    error_message = "database_name must start with a letter and contain only lowercase letters, digits and underscores."
  }
}

variable "master_username" {
  description = "Master user name. The password is generated and stored only in Secrets Manager."
  type        = string
  default     = "studio"

  validation {
    condition     = can(regex("^[a-z][a-z0-9_]{0,15}$", var.master_username)) && !contains(["postgres", "admin", "rdsadmin"], var.master_username)
    error_message = "master_username must be 1-16 lowercase letters, digits or underscores, start with a letter, and not be a reserved name."
  }
}

variable "password_version" {
  description = "Bump to generate a new master password and write it to both RDS and Secrets Manager."
  type        = number
  default     = 1

  validation {
    condition     = var.password_version >= 1 && floor(var.password_version) == var.password_version
    error_message = "password_version must be a positive whole number."
  }
}
