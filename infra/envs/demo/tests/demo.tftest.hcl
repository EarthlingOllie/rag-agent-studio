# The demo environment wires every module with one shared prefix and tag set. CI access (ci-oidc) belongs to infra/bootstrap.
# The network module creates AWS resources, so the AWS provider is mocked: nothing here calls AWS.
mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "123456789012"
    }
  }

  # Real-looking key ARNs, so the data modules' input validation runs against a mocked apply.
  mock_resource "aws_kms_key" {
    defaults = {
      arn = "arn:aws:kms:eu-west-2:123456789012:key/11111111-2222-3333-4444-555555555555"
    }
  }
}

run "wires_every_module_with_the_environment_prefix" {
  command = plan

  assert {
    condition = output.module_names == {
      cache    = "studio-demo-cache"
      cdn      = "studio-demo-cdn"
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

run "wires_the_data_modules_into_the_environment" {
  command = apply

  assert {
    condition     = module.storage.documents_bucket_name == "studio-demo-documents-123456789012" && module.storage.static_bucket_name == "studio-demo-static-123456789012"
    error_message = "The demo buckets must be named from the demo prefix and the account."
  }

  assert {
    condition     = module.storage.documents_cors_allowed_origin == null
    error_message = "Until the cdn module exists, the Documents bucket must allow no cross-origin requests."
  }

  assert {
    condition     = module.kms.credentials_key_alias == "alias/studio-demo-kms-credentials"
    error_message = "The demo's Provider Credentials key must be named from the demo prefix."
  }

  assert {
    condition     = module.database.port == 5432 && module.cache.port == 6379
    error_message = "The database and cache must be wired into the environment."
  }
}

run "rejects_an_unknown_environment" {
  command = plan

  variables {
    environment = "prod"
  }

  expect_failures = [var.environment]
}
