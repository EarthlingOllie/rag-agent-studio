# Bootstrap contract: a versioned, encrypted, private state bucket and a deploy role only this repository can assume.
mock_provider "aws" {
  override_during = plan

  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }

  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }

  mock_resource "aws_kms_key" {
    defaults = { arn = "arn:aws:kms:eu-west-2:123456789012:key/0000aaaa-bb11-cc22-dd33-eeeeee444444" }
  }

  mock_resource "aws_s3_bucket" {
    defaults = { arn = "arn:aws:s3:::rag-agent-studio-tfstate-123456789012" }
  }

  mock_resource "aws_iam_openid_connect_provider" {
    defaults = { arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com" }
  }

  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/rag-agent-studio-github-deploy" }
  }
}

run "names_the_state_bucket_after_the_account" {
  command = plan

  assert {
    condition     = aws_s3_bucket.state.bucket == "rag-agent-studio-tfstate-123456789012"
    error_message = "The state bucket name must be the prefix plus the account ID, so it is globally unique."
  }

  assert {
    condition     = output.state_bucket_name == "rag-agent-studio-tfstate-123456789012"
    error_message = "The bucket name must be an output for the backend configuration."
  }
}

run "versions_the_state_bucket" {
  command = plan

  assert {
    condition     = aws_s3_bucket_versioning.state.versioning_configuration[0].status == "Enabled"
    error_message = "State must be versioned so an earlier state can be recovered."
  }

  assert {
    condition     = aws_s3_bucket_versioning.state.bucket == aws_s3_bucket.state.id
    error_message = "Versioning must apply to the state bucket."
  }

  assert {
    condition     = one(one(aws_s3_bucket_lifecycle_configuration.state.rule).noncurrent_version_expiration).noncurrent_days == 90
    error_message = "Old state versions must be kept for 90 days, then expire."
  }
}

run "encrypts_the_state_bucket_with_a_rotating_key" {
  command = plan

  assert {
    condition     = one(one(aws_s3_bucket_server_side_encryption_configuration.state.rule).apply_server_side_encryption_by_default).sse_algorithm == "aws:kms"
    error_message = "State must be encrypted with KMS."
  }

  assert {
    condition     = one(one(aws_s3_bucket_server_side_encryption_configuration.state.rule).apply_server_side_encryption_by_default).kms_master_key_id == "arn:aws:kms:eu-west-2:123456789012:key/0000aaaa-bb11-cc22-dd33-eeeeee444444"
    error_message = "State must be encrypted with the bootstrap's own key."
  }

  assert {
    condition     = one(aws_s3_bucket_server_side_encryption_configuration.state.rule).bucket_key_enabled
    error_message = "An S3 bucket key keeps KMS request costs down."
  }

  assert {
    condition     = aws_kms_key.state.enable_key_rotation
    error_message = "The state key must rotate."
  }
}

run "keeps_the_state_bucket_private_and_tls_only" {
  command = plan

  assert {
    condition = alltrue([
      aws_s3_bucket_public_access_block.state.block_public_acls,
      aws_s3_bucket_public_access_block.state.block_public_policy,
      aws_s3_bucket_public_access_block.state.ignore_public_acls,
      aws_s3_bucket_public_access_block.state.restrict_public_buckets,
    ])
    error_message = "Every public access block setting must be on."
  }

  assert {
    condition     = one(aws_s3_bucket_ownership_controls.state.rule).object_ownership == "BucketOwnerEnforced"
    error_message = "ACLs must be disabled."
  }

  assert {
    condition = jsondecode(aws_s3_bucket_policy.state.policy).Statement[0] == {
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = ["arn:aws:s3:::rag-agent-studio-tfstate-123456789012", "arn:aws:s3:::rag-agent-studio-tfstate-123456789012/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }
    error_message = "Requests without TLS must be denied."
  }
}

run "outputs_a_native_locking_backend_configuration" {
  command = plan

  assert {
    condition = output.backend_config == {
      bucket       = "rag-agent-studio-tfstate-123456789012"
      region       = "eu-west-2"
      use_lockfile = true
    }
    error_message = "The backend configuration must use S3 native locking."
  }
}

run "lets_only_this_repository_assume_the_deploy_role" {
  command = plan

  assert {
    condition = output.deploy_trust_policy.Statement[0].Condition.StringLike == {
      "token.actions.githubusercontent.com:sub" = [
        "repo:EarthlingOllie/rag-agent-studio:ref:refs/heads/*",
        "repo:EarthlingOllie/rag-agent-studio:pull_request",
        "repo:EarthlingOllie/rag-agent-studio:environment:*",
      ]
    }
    error_message = "Only this repository may assume the deploy role."
  }

  assert {
    condition     = output.deploy_role_arn == "arn:aws:iam::123456789012:role/rag-agent-studio-github-deploy"
    error_message = "The deploy role ARN is the AWS_DEPLOY_ROLE_ARN secret."
  }
}

run "lets_the_deploy_role_use_the_state_and_manage_prefixed_iam_only" {
  command = plan

  assert {
    condition = output.deploy_policy.Statement[0] == {
      Sid      = "ListStateBucket"
      Effect   = "Allow"
      Action   = "s3:ListBucket"
      Resource = "arn:aws:s3:::rag-agent-studio-tfstate-123456789012"
    }
    error_message = "The deploy role may list the state bucket."
  }

  assert {
    condition = output.deploy_policy.Statement[1] == {
      Sid      = "ReadWriteStateAndLockFiles"
      Effect   = "Allow"
      Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
      Resource = "arn:aws:s3:::rag-agent-studio-tfstate-123456789012/*"
    }
    error_message = "The deploy role may read and write state and lock files in the state bucket only."
  }

  assert {
    condition = output.deploy_policy.Statement[2] == {
      Sid      = "UseStateKey"
      Effect   = "Allow"
      Action   = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"]
      Resource = "arn:aws:kms:eu-west-2:123456789012:key/0000aaaa-bb11-cc22-dd33-eeeeee444444"
    }
    error_message = "The deploy role may use the state key."
  }

  assert {
    condition     = alltrue([for arn in output.deploy_policy.Statement[3].Resource : startswith(arn, "arn:aws:iam::123456789012:") && strcontains(arn, "/studio-")])
    error_message = "IAM management must be limited to studio- resources in this account."
  }
}

run "rejects_a_name_prefix_that_would_let_the_role_manage_itself" {
  command = plan

  variables {
    managed_resource_prefix = "rag-"
  }

  expect_failures = [var.managed_resource_prefix]
}
