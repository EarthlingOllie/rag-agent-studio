# Storage module (ticket 09-03): private, encrypted S3 buckets for Documents and for static assets
# (the Studio, the widget and embed.js), served through CloudFront origin access control (ADR-0011).
locals {
  module_name = "storage"
  name        = "${var.name_prefix}-${local.module_name}"
  tags        = merge(var.tags, { Module = local.module_name, ManagedBy = "terraform" })

  buckets = {
    documents = "Uploaded Documents, written through presigned URLs and read by the API and worker"
    static    = "Static Studio and widget builds, served only through CloudFront"
  }
}

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "this" {
  for_each = local.buckets
  #checkov:skip=CKV_AWS_18:Server access logging needs a third bucket and paid storage the short-lived demo does not need.
  #checkov:skip=CKV_AWS_144:Cross-region replication doubles storage cost; the demo is single-region (spec 09, out of scope).
  #checkov:skip=CKV_AWS_21:No versioning: deleting a Document must remove its bytes (spec 03 deletion and retention), and static builds are re-uploaded by every deploy.
  #checkov:skip=CKV_AWS_145:Documents use SSE-KMS with the data key (asserted by the tests); static assets use SSE-S3 so CloudFront needs no KMS grant.
  #checkov:skip=CKV2_AWS_62:No consumer of S3 event notifications exists; ingestion is triggered by the API (spec 03).

  # Bucket names are global, so they carry the account ID.
  bucket        = "${var.name_prefix}-${each.key}-${data.aws_caller_identity.current.account_id}"
  force_destroy = var.force_destroy

  tags = merge(local.tags, { Name = "${var.name_prefix}-${each.key}", Purpose = each.value })
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each = local.buckets

  bucket                  = aws_s3_bucket.this[each.key].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "this" {
  for_each = local.buckets

  bucket = aws_s3_bucket.this[each.key].id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.this["documents"].id

  rule {
    bucket_key_enabled = true

    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
  }
}

# SSE-KMS here would need the key policy to trust CloudFront; static builds are public web assets anyway.
resource "aws_s3_bucket_server_side_encryption_configuration" "static" {
  bucket = aws_s3_bucket.this["static"].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Browsers upload Documents straight to S3 with presigned PUT URLs and read them back with presigned GETs,
# from the Studio's CloudFront origin only.
resource "aws_s3_bucket_cors_configuration" "documents" {
  count = var.documents_cors_allowed_origin == null ? 0 : 1

  bucket = aws_s3_bucket.this["documents"].id

  cors_rule {
    allowed_origins = [var.documents_cors_allowed_origin]
    allowed_methods = ["GET", "PUT"]
    allowed_headers = ["content-type", "content-md5", "x-amz-checksum-sha256", "x-amz-content-sha256", "x-amz-date", "x-amz-security-token"]
    expose_headers  = ["ETag"]
    max_age_seconds = 3600
  }
}

# CloudFront signs every request to the static bucket, which then trusts only that one distribution.
resource "aws_cloudfront_origin_access_control" "static" {
  name                              = "${var.name_prefix}-static"
  description                       = "CloudFront reads of ${var.name_prefix} static assets"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

locals {
  deny_without_tls = {
    for k in keys(local.buckets) : k => {
      Sid       = "DenyRequestsWithoutTls"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.this[k].arn, "${aws_s3_bucket.this[k].arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }
  }

  cloudfront_reads = var.static_assets_distribution_arn == null ? [] : [{
    Sid       = "AllowCloudFrontOriginAccessControlReads"
    Effect    = "Allow"
    Principal = { Service = "cloudfront.amazonaws.com" }
    Action    = "s3:GetObject"
    Resource  = "${aws_s3_bucket.this["static"].arn}/*"
    Condition = { StringEquals = { "AWS:SourceArn" = var.static_assets_distribution_arn } }
  }]
}

# Documents get no bucket grants: the API and worker task roles reach them through IAM (ticket 09-04).
resource "aws_s3_bucket_policy" "documents" {
  bucket = aws_s3_bucket.this["documents"].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [local.deny_without_tls["documents"]] })

  depends_on = [aws_s3_bucket_public_access_block.this]
}

resource "aws_s3_bucket_policy" "static" {
  bucket = aws_s3_bucket.this["static"].id
  policy = jsonencode({ Version = "2012-10-17", Statement = concat([local.deny_without_tls["static"]], local.cloudfront_reads) })

  depends_on = [aws_s3_bucket_public_access_block.this]
}

# Presigned uploads that never finish would otherwise be billed forever. Nothing else expires.
resource "aws_s3_bucket_lifecycle_configuration" "this" {
  for_each = local.buckets

  bucket = aws_s3_bucket.this[each.key].id

  rule {
    id     = "abort-incomplete-multipart-uploads"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}
