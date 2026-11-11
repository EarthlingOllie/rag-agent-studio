# 1.11 is the first Terraform with write-only arguments (password_wo, auth_token_wo, secret_string_wo).
terraform {
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.72"
    }
  }
}
