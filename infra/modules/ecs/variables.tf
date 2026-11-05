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

# --- Network -----------------------------------------------------------------------------------------------------

variable "vpc_id" {
  description = "VPC the ALB and the services run in."
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnets, in two AZs, for the ALB. CloudFront reaches it over the internet (ADR-0011)."
  type        = list(string)

  validation {
    condition     = length(distinct(var.public_subnet_ids)) >= 2
    error_message = "public_subnet_ids must name at least two different subnets (an ALB needs two AZs)."
  }
}

variable "private_subnet_ids" {
  description = "Private subnets the tasks run in. Tasks never get public IPs."
  type        = list(string)

  validation {
    condition     = length(distinct(var.private_subnet_ids)) >= 1
    error_message = "private_subnet_ids must name at least one subnet."
  }
}

# --- Image -------------------------------------------------------------------------------------------------------

variable "image_repository_url" {
  description = "ECR repository URL of the backend image that the API, worker and Beat all run (the ecr module's API repository)."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}\\.dkr\\.ecr\\.[a-z0-9-]+\\.amazonaws\\.com/[a-z0-9._/-]+$", var.image_repository_url))
    error_message = "image_repository_url must be an ECR repository URL, for example 123456789012.dkr.ecr.eu-west-2.amazonaws.com/rag-agent-studio/api."
  }
}

variable "image_repository_arn" {
  description = "ARN of that repository. The execution roles may pull from it and nothing else."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:ecr:[a-z0-9-]+:[0-9]{12}:repository/", var.image_repository_arn))
    error_message = "image_repository_arn must be an ECR repository ARN."
  }
}

variable "image_tag" {
  description = "Image tag to run, normally the git SHA the deploy workflow pushed. Tags are immutable in ECR."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$", var.image_tag)) && var.image_tag != "latest"
    error_message = "image_tag must be a valid Docker tag other than latest (repositories are immutable, so latest would never move)."
  }
}

# --- Sizing ------------------------------------------------------------------------------------------------------

variable "task_sizes" {
  description = "Fargate CPU units and memory (MiB) per service. The worker is sized for Docling (spec 09 cost defaults)."
  type = map(object({
    cpu    = number
    memory = number
  }))
  default = {
    api    = { cpu = 512, memory = 1024 }
    worker = { cpu = 2048, memory = 8192 }
    beat   = { cpu = 256, memory = 512 }
  }

  validation {
    condition     = toset(keys(var.task_sizes)) == toset(["api", "worker", "beat"])
    error_message = "task_sizes must have exactly the keys api, worker and beat."
  }

  # Fargate's allowed CPU and memory pairs: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-tasks-services.html
  validation {
    condition = alltrue([for s in values(var.task_sizes) : (
      s.cpu == 256 ? contains([512, 1024, 2048], s.memory) :
      s.cpu == 512 ? s.memory >= 1024 && s.memory <= 4096 && s.memory % 1024 == 0 :
      s.cpu == 1024 ? s.memory >= 2048 && s.memory <= 8192 && s.memory % 1024 == 0 :
      s.cpu == 2048 ? s.memory >= 4096 && s.memory <= 16384 && s.memory % 1024 == 0 :
      s.cpu == 4096 ? s.memory >= 8192 && s.memory <= 30720 && s.memory % 1024 == 0 :
      s.cpu == 8192 ? s.memory >= 16384 && s.memory <= 61440 && s.memory % 4096 == 0 :
      s.cpu == 16384 ? s.memory >= 32768 && s.memory <= 122880 && s.memory % 8192 == 0 :
      false
    )])
    error_message = "Each task size must be a CPU and memory pair Fargate supports, for example 512 CPU with 1024 to 4096 MiB."
  }
}

variable "desired_counts" {
  description = "Running task count per service. Fixed counts; autoscaling is out of scope (spec 09). Beat must be 0 or 1: two schedulers would run every periodic task twice."
  type = object({
    api    = number
    worker = number
    beat   = number
  })
  default = { api = 1, worker = 1, beat = 1 }

  validation {
    condition     = alltrue([for n in values(var.desired_counts) : n >= 0 && floor(n) == n])
    error_message = "desired_counts must be whole numbers of zero or more."
  }

  validation {
    condition     = var.desired_counts.beat <= 1
    error_message = "desired_counts.beat must be 0 or 1, so periodic tasks are scheduled once."
  }
}

variable "log_retention_days" {
  description = "Days CloudWatch keeps each service's container logs. Short by default to keep the demo cheap."
  type        = number
  default     = 14

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096, 1827, 2192, 2557, 2922, 3288, 3653], var.log_retention_days)
    error_message = "log_retention_days must be a CloudWatch retention value, for example 7, 14 or 30 (never 0, which keeps logs forever)."
  }
}

# --- Data and keys -----------------------------------------------------------------------------------------------

variable "documents_bucket_arn" {
  description = "ARN of the Documents bucket (storage module). Only the API and worker may use its objects."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:s3:::[a-z0-9][a-z0-9.-]+$", var.documents_bucket_arn))
    error_message = "documents_bucket_arn must be an S3 bucket ARN."
  }
}

variable "credentials_key_arn" {
  description = "KMS key for Provider Credential envelope encryption (ADR-0006). The API seals and opens with it; the worker only opens (decrypts)."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:kms:[a-z0-9-]+:[0-9]{12}:key/", var.credentials_key_arn))
    error_message = "credentials_key_arn must be a KMS key ARN."
  }
}

variable "data_key_arn" {
  description = "KMS data key that encrypts the Documents bucket and the platform secrets (kms module)."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:kms:[a-z0-9-]+:[0-9]{12}:key/", var.data_key_arn))
    error_message = "data_key_arn must be a KMS key ARN."
  }
}

variable "database" {
  description = "Connection details of the database module: address, port, name, user, the password secret and its security group."
  type = object({
    address             = string
    port                = number
    name                = string
    username            = string
    password_secret_arn = string
    security_group_id   = string
  })
}

variable "cache" {
  description = "Connection details of the cache module: address, port, the AUTH token secret and its security group."
  type = object({
    address               = string
    port                  = number
    auth_token_secret_arn = string
    security_group_id     = string
  })
}

variable "logfire_token_secret_arn" {
  description = "Optional Secrets Manager secret holding a Logfire write token. When set, every service gets LOGFIRE_TOKEN from it (spec 09 story 23)."
  type        = string
  default     = null

  validation {
    condition     = var.logfire_token_secret_arn == null || can(regex("^arn:aws[a-z-]*:secretsmanager:[a-z0-9-]+:[0-9]{12}:secret:", var.logfire_token_secret_arn))
    error_message = "logfire_token_secret_arn must be a Secrets Manager secret ARN, or null."
  }
}

# --- Edge --------------------------------------------------------------------------------------------------------

variable "origin_header_name" {
  description = "Header CloudFront adds to every origin request. The ALB forwards only requests that carry it with the secret value (ADR-0011)."
  type        = string
  default     = "X-Origin-Verify"

  validation {
    condition     = can(regex("^[A-Za-z0-9-]{1,40}$", var.origin_header_name))
    error_message = "origin_header_name must be an HTTP header name of letters, digits and hyphens."
  }
}

variable "origin_secret_version" {
  description = "Bump to generate a new origin header secret. The cdn module must be applied in the same run so CloudFront sends the new value."
  type        = number
  default     = 1

  validation {
    condition     = var.origin_secret_version >= 1 && floor(var.origin_secret_version) == var.origin_secret_version
    error_message = "origin_secret_version must be a positive whole number."
  }
}

variable "session_secret_version" {
  description = "Bump to generate a new session-signing secret. Bumping it signs every Member out."
  type        = number
  default     = 1

  validation {
    condition     = var.session_secret_version >= 1 && floor(var.session_secret_version) == var.session_secret_version
    error_message = "session_secret_version must be a positive whole number."
  }
}

variable "alb_deletion_protection" {
  description = "Block deletion of the ALB. Off for the demo so it can be destroyed in one run (spec 09 story 27)."
  type        = bool
  default     = false
}
