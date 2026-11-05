terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.72"
    }
  }

  # No backend: the bootstrap runs once, by hand, with local state, because the bucket it creates does not exist yet.
  # docs/infra-bootstrap.md explains how to keep or migrate that state.
}
