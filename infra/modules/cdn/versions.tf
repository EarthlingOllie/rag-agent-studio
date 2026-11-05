# 6.x gives resources a region argument, which puts the CloudFront certificate in us-east-1 without a second provider.
terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.72"
    }
  }
}
