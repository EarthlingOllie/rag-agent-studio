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

variable "vpc_cidr" {
  description = "IPv4 CIDR block of the VPC. A /16 leaves room for /24 public and /20 private subnets."
  type        = string
  default     = "10.0.0.0/16"

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0)) && can(regex("^[0-9.]+/(1[6-9]|20)$", var.vpc_cidr))
    error_message = "vpc_cidr must be an IPv4 CIDR block of /16 to /20."
  }
}

variable "managed_nat" {
  description = "Use a managed NAT gateway instead of the default single fck-nat instance (ADR-0010)."
  type        = bool
  default     = false
}

variable "fck_nat_instance_type" {
  description = "EC2 instance type for fck-nat. Must be a Graviton (arm64) type to match the fck-nat AMI."
  type        = string
  default     = "t4g.nano"

  validation {
    condition     = can(regex("^[a-z][0-9]+g[a-z]*\\.[a-z0-9]+$", var.fck_nat_instance_type))
    error_message = "fck_nat_instance_type must be a Graviton (arm64) type such as t4g.nano."
  }
}

variable "availability_zones" {
  description = "The two availability zones the VPC spans, for example [\"eu-west-2a\", \"eu-west-2b\"]. Named explicitly so a new AWS zone never changes the plan."
  type        = list(string)

  validation {
    condition     = length(var.availability_zones) == 2 && length(distinct(var.availability_zones)) == 2
    error_message = "availability_zones must name exactly two different availability zones."
  }
}
