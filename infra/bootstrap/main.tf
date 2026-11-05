# One-time bootstrap (spec 09, user story 4): the Terraform state bucket that every environment's S3 backend uses,
# and the GitHub OIDC deploy role that CI assumes. Applied once, by hand, with local state. See docs/infra-bootstrap.md.
provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.tags
  }
}

data "aws_caller_identity" "current" {}

data "aws_partition" "current" {}

locals {
  tags       = { Project = "rag-agent-studio", Environment = "shared", ManagedBy = "terraform" }
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition
  iam_arn    = "arn:${local.partition}:iam::${local.account_id}"

  deploy_policy = {
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ListStateBucket"
        Effect   = "Allow"
        Action   = "s3:ListBucket"
        Resource = aws_s3_bucket.state.arn
      },
      {
        # Native locking writes and deletes a .tflock object next to each state file.
        Sid      = "ReadWriteStateAndLockFiles"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "${aws_s3_bucket.state.arn}/*"
      },
      {
        Sid      = "UseStateKey"
        Effect   = "Allow"
        Action   = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"]
        Resource = aws_kms_key.state.arn
      },
      {
        # PowerUserAccess excludes IAM. Environments create their own task roles, so the role may manage IAM
        # resources whose names start with managed_resource_prefix, and nothing else (not itself).
        Sid    = "ManagePrefixedIamResources"
        Effect = "Allow"
        Action = [
          "iam:AttachRolePolicy", "iam:CreatePolicy", "iam:CreatePolicyVersion", "iam:CreateRole",
          "iam:DeletePolicy", "iam:DeletePolicyVersion", "iam:DeleteRole", "iam:DeleteRolePolicy",
          "iam:DetachRolePolicy", "iam:GetPolicy", "iam:GetPolicyVersion", "iam:GetRole", "iam:GetRolePolicy",
          "iam:ListAttachedRolePolicies", "iam:ListInstanceProfilesForRole", "iam:ListPolicyVersions",
          "iam:ListRolePolicies", "iam:ListRoleTags", "iam:PassRole", "iam:PutRolePolicy", "iam:TagPolicy",
          "iam:TagRole", "iam:UntagPolicy", "iam:UntagRole", "iam:UpdateAssumeRolePolicy", "iam:UpdateRole",
        ]
        Resource = [
          "${local.iam_arn}:role/${var.managed_resource_prefix}*",
          "${local.iam_arn}:policy/${var.managed_resource_prefix}*",
        ]
      },
      {
        # PowerUserAccess would otherwise let CI delete or open up the state it depends on.
        Sid    = "ProtectStateBucketAndKey"
        Effect = "Deny"
        Action = [
          "s3:DeleteBucket", "s3:DeleteBucketPolicy", "s3:PutBucketPolicy", "s3:PutBucketVersioning",
          "s3:PutEncryptionConfiguration", "s3:PutBucketPublicAccessBlock", "s3:PutLifecycleConfiguration",
          "kms:DisableKey", "kms:DisableKeyRotation", "kms:PutKeyPolicy", "kms:ScheduleKeyDeletion",
        ]
        Resource = [aws_s3_bucket.state.arn, aws_kms_key.state.arn]
      },
    ]
  }
}

resource "aws_kms_key" "state" {
  description             = "Encrypts Terraform state for rag-agent-studio."
  enable_key_rotation     = true
  deletion_window_in_days = 30
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      # The account administers the key; access for principals is granted through IAM policies.
      Sid       = "AccountAdministersKey"
      Effect    = "Allow"
      Principal = { AWS = "${local.iam_arn}:root" }
      Action    = "kms:*"
      Resource  = "*"
    }]
  })

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_kms_alias" "state" {
  name          = "alias/${var.name_prefix}-tfstate"
  target_key_id = aws_kms_key.state.key_id
}

resource "aws_s3_bucket" "state" {
  # checkov:skip=CKV_AWS_18:Access logging would need a second bucket; CloudTrail covers the few hands that touch state.
  # checkov:skip=CKV_AWS_144:Cross-region replication is out of scope for a single-region demo (spec 09, Out of Scope).
  # checkov:skip=CKV2_AWS_62:No consumer for event notifications on state objects.
  bucket = "${var.name_prefix}-tfstate-${local.account_id}"

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    bucket_key_enabled = true

    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.state.arn
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    id     = "expire-old-state-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 90
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  depends_on = [aws_s3_bucket_versioning.state]
}

resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })

  depends_on = [aws_s3_bucket_public_access_block.state]
}

module "ci_oidc" {
  source = "../modules/ci-oidc"

  name_prefix                = var.name_prefix
  tags                       = local.tags
  github_repository          = var.github_repository
  existing_oidc_provider_arn = var.existing_oidc_provider_arn
  managed_policy_arns        = var.deploy_managed_policy_arns
  inline_policy_json         = jsonencode(local.deploy_policy)
}
