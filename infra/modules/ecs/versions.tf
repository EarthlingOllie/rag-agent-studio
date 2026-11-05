# 1.11 is the first Terraform with write-only arguments (the session secret uses secret_string_wo).
terraform {
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.72"
    }
  }
}
