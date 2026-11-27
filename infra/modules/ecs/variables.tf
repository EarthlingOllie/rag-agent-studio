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

variable "vpc_cidr" {
  description = "The VPC's IPv4 CIDR. The ALB connects to the API from inside it, so the API trusts X-Forwarded-For from it."
  type        = string

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0)) && strcontains(var.vpc_cidr, "/")
    error_message = "vpc_cidr must be a CIDR block, such as 10.0.0.0/16."
  }
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
  description = "ECR repository URL of the backend image that the API, both worker pools and Beat all run (the ecr module's API repository). An emulator's path-style registry, localhost:<port>/<account>/<region>/<repository>, is accepted too (ticket 23-01)."
  type        = string

  validation {
    condition = (
      can(regex("^[0-9]{12}\\.dkr\\.ecr\\.[a-z0-9-]+\\.amazonaws\\.com/[a-z0-9._/-]+$", var.image_repository_url)) ||
      can(regex("^localhost:[0-9]{1,5}/[0-9]{12}/[a-z0-9-]+/[a-z0-9._/-]+$", var.image_repository_url))
    )
    error_message = "image_repository_url must be an ECR repository URL, for example 123456789012.dkr.ecr.eu-west-2.amazonaws.com/rag-agent-studio/api, or an emulator's path-style one, localhost:4566/000000000000/eu-west-2/rag-agent-studio/api."
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

variable "cpu_architecture" {
  description = "CPU architecture of every task definition (the services, the migration and the seed task). ARM64 (Graviton) on AWS; an emulator on an Intel host needs X86_64 (ticket 23-01). The image must be built for it."
  type        = string
  default     = "ARM64"

  validation {
    condition     = contains(["ARM64", "X86_64"], var.cpu_architecture)
    error_message = "cpu_architecture must be ARM64 or X86_64, the values Fargate accepts."
  }
}

variable "extra_environment" {
  description = "Plain environment variables added to every container the module runs (the four services, the migration and the seed task), for settings an environment needs beyond the module's, such as SSL_CERT_FILE pointing at an emulator's CA (ticket 23-02). They may not replace a setting the module sets. Never secrets: values are stored in the task definitions in plain text."
  type        = map(string)
  default     = {}
  nullable    = false

  validation {
    condition     = alltrue([for name in keys(var.extra_environment) : can(regex("^[A-Za-z_][A-Za-z0-9_]*$", name))])
    error_message = "extra_environment names must be environment variable names: letters, digits and underscores, not starting with a digit."
  }
}

# --- Sizing ------------------------------------------------------------------------------------------------------

variable "task_sizes" {
  description = "Fargate CPU units and memory (MiB) per service (spec 22 sizes). The general pool is sized for Docling converting the largest Document; the runs pool for two Run processes (--concurrency=2) with the local Embedding Model and the Guardrail classifier loaded, which ticket 22-04 measured at about 4.7 GB."
  type = map(object({
    cpu    = number
    memory = number
  }))
  default = {
    api              = { cpu = 512, memory = 1024 }
    "worker-general" = { cpu = 2048, memory = 8192 }
    "worker-runs"    = { cpu = 1024, memory = 6144 }
    beat             = { cpu = 256, memory = 512 }
  }

  validation {
    condition     = toset(keys(var.task_sizes)) == toset(["api", "worker-general", "worker-runs", "beat"])
    error_message = "task_sizes must have exactly the keys api, worker-general, worker-runs and beat."
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
  description = "Task count of each service when Terraform creates it. Afterwards autoscaling owns the API's and the worker pools' counts and Terraform ignores changes here (ticket 22-05), so each must lie within that service's scaling bounds. Beat is not scaled and must be 0 or 1: two schedulers would run every periodic task twice."
  type = object({
    api            = number
    worker-general = number
    worker-runs    = number
    beat           = number
  })
  default = { api = 1, "worker-general" = 1, "worker-runs" = 0, beat = 1 }

  validation {
    condition     = alltrue([for n in values(var.desired_counts) : n >= 0 && floor(n) == n])
    error_message = "desired_counts must be whole numbers of zero or more."
  }

  validation {
    condition     = var.desired_counts.beat <= 1
    error_message = "desired_counts.beat must be 0 or 1, so periodic tasks are scheduled once."
  }

  validation {
    condition     = alltrue([for k in ["api", "worker-general", "worker-runs"] : var.desired_counts[k] >= var.scaling[k].min && var.desired_counts[k] <= var.scaling[k].max])
    error_message = "desired_counts for api, worker-general and worker-runs must lie within that service's scaling minimum and maximum."
  }
}

variable "scaling" {
  description = <<-EOT
    Application Auto Scaling bounds, targets and cooldowns (ticket 22-05, ADR-0021). Every attribute is optional.
    api: min and max tasks, cpu_target (average CPU %, target tracking) and the scale-out and scale-in cooldowns (seconds).
    worker-general and worker-runs: min and max tasks; jobs_per_task, the slots a task has (its Celery --concurrency),
    so a pool runs one task per jobs_per_task jobs waiting or in flight on its queue; the cooldowns of stepping up and
    of going back to the minimum; and idle_minutes, how long the queue must hold no job before the pool returns to its
    minimum. The runs pool's minimum is zero; the general pool's is at least one, as it runs the sweeper and the
    scheduled jobs. Beat is not scaled.
  EOT
  type = object({
    api = optional(object({
      min                = optional(number, 1)
      max                = optional(number, 3)
      cpu_target         = optional(number, 60)
      scale_out_cooldown = optional(number, 60)
      scale_in_cooldown  = optional(number, 300)
    }), {})
    worker-general = optional(object({
      min                = optional(number, 1)
      max                = optional(number, 3)
      jobs_per_task      = optional(number, 2)
      scale_out_cooldown = optional(number, 60)
      scale_in_cooldown  = optional(number, 300)
      idle_minutes       = optional(number, 5)
    }), {})
    worker-runs = optional(object({
      min                = optional(number, 0)
      max                = optional(number, 2)
      jobs_per_task      = optional(number, 2)
      scale_out_cooldown = optional(number, 60)
      scale_in_cooldown  = optional(number, 300)
      idle_minutes       = optional(number, 5)
    }), {})
  })
  default  = {}
  nullable = false

  validation {
    condition = alltrue([for s in values(var.scaling) : (
      s.min >= 0 && floor(s.min) == s.min && s.max >= 1 && floor(s.max) == s.max && s.max >= s.min &&
      s.scale_out_cooldown >= 0 && s.scale_in_cooldown >= 0
    )])
    error_message = "Each scaling minimum must be a whole number of zero or more, each maximum a whole number of at least one and no less than the minimum, and cooldowns zero or more seconds."
  }

  validation {
    condition     = var.scaling["worker-general"].min >= 1
    error_message = "scaling.worker-general.min must be at least 1: the general pool runs the sweeper and the scheduled jobs (ADR-0021)."
  }

  validation {
    condition     = var.scaling.api.cpu_target > 0 && var.scaling.api.cpu_target <= 100
    error_message = "scaling.api.cpu_target must be a CPU percentage above 0 and at most 100."
  }

  validation {
    condition = alltrue([for k in ["worker-general", "worker-runs"] : (
      var.scaling[k].jobs_per_task >= 1 && floor(var.scaling[k].jobs_per_task) == var.scaling[k].jobs_per_task &&
      var.scaling[k].idle_minutes >= 1 && floor(var.scaling[k].idle_minutes) == var.scaling[k].idle_minutes
    )])
    error_message = "Each worker pool's jobs_per_task and idle_minutes must be whole numbers of at least 1."
  }
}

variable "worker_spot" {
  description = "Run the general worker pool on Fargate Spot (its jobs restart for free). Set false to move it to regular Fargate, for example during a Spot shortage: ECS does not fall back by itself (spec 22 story 10). The runs pool always uses regular Fargate."
  type        = bool
  default     = true
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
  description = "ARN of the Documents bucket (storage module). Only the API, the general worker pool and the seed task may use its objects."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:s3:::[a-z0-9][a-z0-9.-]+$", var.documents_bucket_arn))
    error_message = "documents_bucket_arn must be an S3 bucket ARN."
  }
}

variable "credentials_key_arn" {
  description = "KMS key for Provider Credential envelope encryption (ADR-0006). The API seals and opens with it; the worker pools only open (decrypt)."
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
  description = "Connection details of the database module: address, port, name, user, the password secret and its security group. tls (default true) makes every container connect over TLS, which the database module's parameter group forces on AWS; an emulator whose database serves no TLS needs false (ticket 23-03)."
  type = object({
    address             = string
    port                = number
    name                = string
    username            = string
    password_secret_arn = string
    security_group_id   = string
    tls                 = optional(bool, true)
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

variable "queues" {
  description = "The queue module's general and runs queues: name and URL (the services' settings) and ARN (task role policies)."
  type = object({
    general = object({ name = string, url = string, arn = string })
    runs    = object({ name = string, url = string, arn = string })
  })

  validation {
    condition = alltrue([for q in values(var.queues) :
      can(regex("^arn:aws[a-z-]*:sqs:[a-z0-9-]+:[0-9]{12}:[A-Za-z0-9_-]{1,80}$", q.arn)) && endswith(q.arn, ":${q.name}") && startswith(q.url, "https://") && endswith(q.url, "/${q.name}")
    ])
    error_message = "queues must give each queue's name, its https URL and its SQS queue ARN, all for the same queue."
  }
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

variable "key_wrapper_secret_version" {
  description = "Bump to generate a new LOCAL_KEY_WRAPPER_KEY, which signs widget tokens. Bumping it invalidates every issued widget token."
  type        = number
  default     = 1

  validation {
    condition     = var.key_wrapper_secret_version >= 1 && floor(var.key_wrapper_secret_version) == var.key_wrapper_secret_version
    error_message = "key_wrapper_secret_version must be a positive whole number."
  }
}

variable "demo_pages" {
  description = "Turn on the API's demo page routes (DEMO_PAGES, ticket 10-03): the demo pages under /demo/ ask them which seeded Agents to embed. Only for a demo environment."
  type        = bool
  default     = false
}

variable "studio_url" {
  description = "The Studio's public HTTPS address (the cdn module's url). The API and the worker pools put it in links in emails."
  type        = string

  validation {
    condition     = can(regex("^https://[a-z0-9.-]+$", var.studio_url))
    error_message = "studio_url must be an https:// origin with no path, for example https://d111111abcdef8.cloudfront.net."
  }
}

variable "alb_deletion_protection" {
  description = "Block deletion of the ALB. Off for the demo so it can be destroyed in one run (spec 09 story 27)."
  type        = bool
  default     = false
}

variable "migration_task_size" {
  description = "Fargate CPU units and memory (MiB) of the one-off migration task (ticket 09-06)."
  type = object({
    cpu    = number
    memory = number
  })
  default = { cpu = 256, memory = 512 }

  # Fargate's allowed pairs up to 1 vCPU: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-tasks-services.html
  validation {
    condition = (
      var.migration_task_size.cpu == 256 ? contains([512, 1024, 2048], var.migration_task_size.memory) :
      var.migration_task_size.cpu == 512 ? var.migration_task_size.memory >= 1024 && var.migration_task_size.memory <= 4096 && var.migration_task_size.memory % 1024 == 0 :
      var.migration_task_size.cpu == 1024 ? var.migration_task_size.memory >= 2048 && var.migration_task_size.memory <= 8192 && var.migration_task_size.memory % 1024 == 0 :
      false
    )
    error_message = "migration_task_size must be a Fargate CPU and memory pair of at most 1 vCPU, such as 256 and 512."
  }
}

variable "seed_task_size" {
  description = "Fargate CPU units and memory (MiB) of the one-off seed task (ticket 10-05). It runs the API in process, with the local Embedding Model and the Guardrail classifier."
  type = object({
    cpu    = number
    memory = number
  })
  default = { cpu = 1024, memory = 4096 }

  # Fargate's allowed pairs from 1 to 4 vCPU: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-tasks-services.html
  validation {
    condition = (
      var.seed_task_size.cpu == 1024 ? var.seed_task_size.memory >= 2048 && var.seed_task_size.memory <= 8192 && var.seed_task_size.memory % 1024 == 0 :
      var.seed_task_size.cpu == 2048 ? var.seed_task_size.memory >= 4096 && var.seed_task_size.memory <= 16384 && var.seed_task_size.memory % 1024 == 0 :
      var.seed_task_size.cpu == 4096 ? var.seed_task_size.memory >= 8192 && var.seed_task_size.memory <= 30720 && var.seed_task_size.memory % 1024 == 0 :
      false
    )
    error_message = "seed_task_size must be a Fargate CPU and memory pair of 1 to 4 vCPU, such as 1024 and 4096."
  }
}
