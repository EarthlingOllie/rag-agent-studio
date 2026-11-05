# Module contract for the kms module (ticket 09-03), at the module seam, with a mocked AWS provider.
mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "123456789012"
    }
  }

  mock_data "aws_partition" {
    defaults = {
      partition = "aws"
    }
  }
}

variables {
  name_prefix = "studio-demo"
  tags        = { Environment = "demo", Project = "rag-agent-studio" }
}

run "every_key_rotates_yearly" {
  command = plan

  assert {
    condition     = alltrue([for k in aws_kms_key.this : k.enable_key_rotation])
    error_message = "Every KMS key must have automatic rotation enabled."
  }

  assert {
    condition     = alltrue([for k in aws_kms_key.this : k.rotation_period_in_days == 365])
    error_message = "Keys must rotate yearly by default."
  }

  assert {
    condition     = toset(keys(aws_kms_key.this)) == toset(["credentials", "data"])
    error_message = "The module must create the credentials key (ADR-0006) and the data-at-rest key."
  }
}

run "key_policy_trusts_only_this_account" {
  command = plan

  assert {
    condition = alltrue([for k in aws_kms_key.this : jsondecode(k.policy).Statement == [{
      Sid       = "EnableIamPoliciesInThisAccount"
      Effect    = "Allow"
      Principal = { AWS = "arn:aws:iam::123456789012:root" }
      Action    = "kms:*"
      Resource  = "*"
    }]])
    error_message = "Each key policy must delegate to IAM in this account only, with no other principal."
  }

  assert {
    condition     = alltrue([for k in aws_kms_key.this : k.key_usage == "ENCRYPT_DECRYPT" && k.deletion_window_in_days == 7])
    error_message = "Keys must be symmetric encryption keys with the short demo deletion window."
  }
}

run "outputs_name_each_key_from_the_prefix" {
  command = plan

  assert {
    condition     = output.credentials_key_alias == "alias/studio-demo-kms-credentials"
    error_message = "The credentials key alias must be derived from name_prefix."
  }

  assert {
    condition     = aws_kms_alias.this["data"].name == "alias/studio-demo-kms-data"
    error_message = "The data key alias must be derived from name_prefix."
  }

  assert {
    condition     = output.name == "studio-demo-kms"
    error_message = "The kms name must be derived from name_prefix."
  }
}

run "outputs_each_key_arn" {
  command = apply

  assert {
    condition     = output.credentials_key_arn == aws_kms_key.this["credentials"].arn && output.data_key_arn == aws_kms_key.this["data"].arn
    error_message = "The module must output the ARN of each key."
  }

  assert {
    condition     = output.credentials_key_arn != output.data_key_arn
    error_message = "Provider Credentials must not share a key with data at rest."
  }

  assert {
    condition     = alltrue([for a in aws_kms_alias.this : a.target_key_id == aws_kms_key.this[trimprefix(a.name, "alias/studio-demo-kms-")].key_id])
    error_message = "Each alias must point at its own key."
  }
}

run "every_resource_carries_the_standard_tags" {
  command = plan

  assert {
    condition     = output.tags == { Environment = "demo", Project = "rag-agent-studio", Module = "kms", ManagedBy = "terraform" }
    error_message = "Tags must merge the caller's tags with the module's own."
  }

  assert {
    condition     = alltrue([for k in aws_kms_key.this : alltrue([for key, value in output.tags : lookup(k.tags, key, null) == value])])
    error_message = "Every key must carry the standard tags."
  }
}

run "rotation_period_is_configurable" {
  command = plan

  variables {
    rotation_period_in_days = 90
  }

  assert {
    condition     = alltrue([for k in aws_kms_key.this : k.rotation_period_in_days == 90 && k.enable_key_rotation])
    error_message = "rotation_period_in_days must reach every key."
  }
}

run "rejects_a_rotation_period_aws_does_not_allow" {
  command = plan

  variables {
    rotation_period_in_days = 89
  }

  expect_failures = [var.rotation_period_in_days]
}

run "rejects_a_rotation_period_over_the_aws_maximum" {
  command = plan

  variables {
    rotation_period_in_days = 2561
  }

  expect_failures = [var.rotation_period_in_days]
}

run "rejects_a_deletion_window_under_seven_days" {
  command = plan

  variables {
    deletion_window_in_days = 6
  }

  expect_failures = [var.deletion_window_in_days]
}

run "rejects_a_deletion_window_over_thirty_days" {
  command = plan

  variables {
    deletion_window_in_days = 31
  }

  expect_failures = [var.deletion_window_in_days]
}

run "rejects_tags_without_project_and_environment" {
  command = plan

  variables {
    tags = { Environment = "demo" }
  }

  expect_failures = [var.tags]
}

run "rejects_an_invalid_prefix" {
  command = plan

  variables {
    name_prefix = "Studio_Demo"
  }

  expect_failures = [var.name_prefix]
}
