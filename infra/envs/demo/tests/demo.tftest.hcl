# The demo environment wires every module with one shared prefix and tag set.
# The network module creates AWS resources, so the AWS provider is mocked: nothing here calls AWS.
mock_provider "aws" {}

run "wires_every_module_with_the_environment_prefix" {
  command = plan

  assert {
    condition = output.module_names == {
      cache    = "studio-demo-cache"
      cdn      = "studio-demo-cdn"
      ci_oidc  = "studio-demo-ci-oidc"
      database = "studio-demo-database"
      ecs      = "studio-demo-ecs"
      kms      = "studio-demo-kms"
      network  = "studio-demo-network"
      storage  = "studio-demo-storage"
    }
    error_message = "Every module must be named from the demo prefix."
  }

  assert {
    condition     = output.tags == { Environment = "demo", Project = "rag-agent-studio" }
    error_message = "The environment's tags must carry the environment and project."
  }

  assert {
    condition     = module.network.nat_mode == "fck-nat"
    error_message = "The demo environment must egress through fck-nat (ADR-0010)."
  }

  assert {
    condition     = module.network.availability_zones == tolist(["eu-west-2a", "eu-west-2b"])
    error_message = "The demo VPC must span two AZs of its region."
  }
}

run "rejects_an_unknown_environment" {
  command = plan

  variables {
    environment = "prod"
  }

  expect_failures = [var.environment]
}
