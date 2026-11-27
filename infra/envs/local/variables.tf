variable "environment" {
  description = "Environment name. Only local exists: the rehearsal on the Floci emulator (spec 23)."
  type        = string
  default     = "local"

  validation {
    condition     = contains(["local"], var.environment)
    error_message = "environment must be local."
  }
}

variable "aws_region" {
  description = "Region the emulator is told to act as. Matches the demo's, so the rehearsal names everything as the demo does."
  type        = string
  default     = "eu-west-2"

  validation {
    condition     = can(regex("^[a-z]{2}(-[a-z]+)+-[0-9]$", var.aws_region))
    error_message = "aws_region must be an AWS region name such as eu-west-2."
  }
}

variable "image_tag" {
  description = "Backend image tag the services and the migration task run. scripts/deploy/rehearse.sh sets it (default rehearsal); bootstrap is only a placeholder for plans and tests."
  type        = string
  default     = "bootstrap"
}

variable "cpu_architecture" {
  description = "CPU architecture of every task: the machine's own, as the emulator runs tasks as containers on it and refuses an image of another architecture (ticket 23-01). scripts/deploy/rehearse.sh passes ARM64 on Apple-silicon and other ARM64 machines."
  type        = string
  default     = "X86_64"

  validation {
    condition     = contains(["X86_64", "ARM64"], var.cpu_architecture)
    error_message = "cpu_architecture must be X86_64 or ARM64."
  }
}

variable "emulator_port" {
  description = "The host port the rehearsal publishes Floci on, through its front end (infra/rehearsal/compose.yml). Floci serves the emulated distribution over plain HTTP on this port (ticket 23-01); its health check and queue URLs assume 4566."
  type        = number
  default     = 4566

  validation {
    condition     = var.emulator_port > 0 && var.emulator_port < 65536 && floor(var.emulator_port) == var.emulator_port
    error_message = "emulator_port must be a TCP port number."
  }
}

variable "ca_bundle_path" {
  description = "Where the rehearsal's backend image keeps its CA bundle, which includes Floci's root CA (the emulator gives its tasks none, ticket 23-01). infra/rehearsal/ca.Dockerfile writes it there; every container is pointed at it."
  type        = string
  default     = "/etc/ssl/certs/ca-certificates.crt"

  validation {
    condition     = startswith(var.ca_bundle_path, "/")
    error_message = "ca_bundle_path must be an absolute path inside the image."
  }
}

variable "emulator_endpoint" {
  description = "Floci's address as terraform sees it: the rehearsal runs terraform on its tools network, where Floci answers as floci. Every service the modules use is pinned to it, so this environment never reaches AWS."
  type        = string
  default     = "http://floci:4566"

  validation {
    condition     = can(regex("^https?://[a-z0-9.-]+(:[0-9]{1,5})?$", var.emulator_endpoint))
    error_message = "emulator_endpoint must be an http:// or https:// address with no path, such as http://floci:4566."
  }
}
