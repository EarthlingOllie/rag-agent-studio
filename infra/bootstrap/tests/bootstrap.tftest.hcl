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

run "lets_the_deploy_role_manage_queues_named_for_this_project_only" {
  command = plan

  assert {
    condition = [for st in output.deploy_policy.Statement : st if st.Sid == "ManageProjectQueues"] == [{
      Sid    = "ManageProjectQueues"
      Effect = "Allow"
      Action = [
        "sqs:CreateQueue", "sqs:DeleteQueue", "sqs:GetQueueAttributes", "sqs:GetQueueUrl", "sqs:ListDeadLetterSourceQueues",
        "sqs:ListQueueTags", "sqs:SetQueueAttributes", "sqs:TagQueue", "sqs:UntagQueue",
      ]
      Resource = "arn:aws:sqs:*:123456789012:studio-*"
    }]
    error_message = "The deploy role may manage the queues environments create (studio-*) in this account (ticket 22-02)."
  }

  assert {
    condition = [for st in output.deploy_policy.Statement : st if st.Sid == "NoOtherQueues"] == [{
      Sid         = "NoOtherQueues"
      Effect      = "Deny"
      Action      = "sqs:*"
      NotResource = "arn:aws:sqs:*:123456789012:studio-*"
    }]
    error_message = "PowerUserAccess would otherwise let CI touch any queue: every queue not named for this project must be denied."
  }
}

run "lets_the_deploy_role_manage_scaling_of_this_projects_services_only" {
  command = plan

  assert {
    condition = [for st in output.deploy_policy.Statement : st if st.Sid == "ManageScalingOfEcsServices"] == [{
      Sid    = "ManageScalingOfEcsServices"
      Effect = "Allow"
      Action = [
        "application-autoscaling:DeleteScalingPolicy", "application-autoscaling:DeregisterScalableTarget",
        "application-autoscaling:DescribeScalableTargets", "application-autoscaling:DescribeScalingActivities",
        "application-autoscaling:DescribeScalingPolicies", "application-autoscaling:ListTagsForResource",
        "application-autoscaling:PutScalingPolicy", "application-autoscaling:RegisterScalableTarget",
        "application-autoscaling:TagResource", "application-autoscaling:UntagResource",
      ]
      Resource  = "*"
      Condition = { StringEquals = { "application-autoscaling:service-namespace" = "ecs" } }
    }]
    error_message = "The deploy role may manage scalable targets and scaling policies of ECS services (ticket 22-05)."
  }

  assert {
    condition = [for st in output.deploy_policy.Statement : st if st.Sid == "UpdateProjectServices"] == [{
      Sid      = "UpdateProjectServices"
      Effect   = "Allow"
      Action   = ["ecs:DescribeServices", "ecs:UpdateService"]
      Resource = "arn:aws:ecs:*:123456789012:service/studio-*/studio-*"
    }]
    error_message = "Registering an ECS service's scalable target needs DescribeServices and UpdateService on that service: allowed on this project's services."
  }

  assert {
    condition = [for st in output.deploy_policy.Statement : st if st.Sid == "NoOtherServices"] == [{
      Sid         = "NoOtherServices"
      Effect      = "Deny"
      Action      = ["ecs:DeleteService", "ecs:UpdateService"]
      NotResource = "arn:aws:ecs:*:123456789012:service/studio-*/studio-*"
    }]
    error_message = "PowerUserAccess would otherwise let CI change, or register scaling on, any ECS service: every service not named for this project must be denied."
  }

  assert {
    condition = [for st in output.deploy_policy.Statement : st if st.Sid == "NoScalingOfOtherResources"] == [{
      Sid    = "NoScalingOfOtherResources"
      Effect = "Deny"
      Action = [
        "application-autoscaling:DeleteScalingPolicy", "application-autoscaling:DeregisterScalableTarget",
        "application-autoscaling:PutScalingPolicy", "application-autoscaling:RegisterScalableTarget",
      ]
      Resource  = "*"
      Condition = { StringNotEqualsIfExists = { "application-autoscaling:service-namespace" = "ecs" } }
    }]
    error_message = "CI may not change scaling of anything but ECS services."
  }
}

run "lets_the_deploy_role_read_and_clear_task_protection_in_this_projects_clusters_only" {
  command = plan

  assert {
    condition = [for st in output.deploy_policy.Statement : st if st.Sid == "ReadAndClearProjectTaskProtection"] == [{
      Sid      = "ReadAndClearProjectTaskProtection"
      Effect   = "Allow"
      Action   = ["ecs:GetTaskProtection", "ecs:UpdateTaskProtection"]
      Resource = "arn:aws:ecs:*:123456789012:task/studio-*/*"
    }]
    error_message = "The deploy script reads and clears protection on old worker tasks in this project's clusters (ticket 22-06)."
  }

  assert {
    condition = [for st in output.deploy_policy.Statement : st if st.Sid == "NoOtherTaskProtection"] == [{
      Sid         = "NoOtherTaskProtection"
      Effect      = "Deny"
      Action      = ["ecs:GetTaskProtection", "ecs:UpdateTaskProtection"]
      NotResource = "arn:aws:ecs:*:123456789012:task/studio-*/*"
    }]
    error_message = "PowerUserAccess would otherwise let CI change protection on any task: tasks outside this project's clusters must be denied."
  }
}

run "rejects_a_name_prefix_that_would_let_the_role_manage_itself" {
  command = plan

  variables {
    managed_resource_prefix = "rag-"
  }

  expect_failures = [var.managed_resource_prefix]
}
