# Module contract for the storage module (ticket 09-03), at the module seam, with a mocked AWS provider.
# Runs that compare resource IDs use `command = apply`: the mock provider only invents IDs at apply time,
# and it never calls AWS, so apply here creates nothing real.
mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "123456789012"
    }
  }
}

variables {
  name_prefix = "studio-demo"
  tags        = { Environment = "demo", Project = "rag-agent-studio" }
  kms_key_arn = "arn:aws:kms:eu-west-2:123456789012:key/11111111-2222-3333-4444-555555555555"
}

run "both_buckets_are_private_and_encrypted" {
  command = apply

  assert {
    condition     = toset(keys(aws_s3_bucket.this)) == toset(["documents", "static"])
    error_message = "The module must create the Documents bucket and the static assets bucket."
  }

  assert {
    condition = alltrue([for k, b in aws_s3_bucket.this :
      aws_s3_bucket_public_access_block.this[k].bucket == b.id &&
      aws_s3_bucket_public_access_block.this[k].block_public_acls &&
      aws_s3_bucket_public_access_block.this[k].block_public_policy &&
      aws_s3_bucket_public_access_block.this[k].ignore_public_acls &&
      aws_s3_bucket_public_access_block.this[k].restrict_public_buckets
    ])
    error_message = "Every bucket must block all public access."
  }

  assert {
    condition     = alltrue([for k, b in aws_s3_bucket.this : aws_s3_bucket_ownership_controls.this[k].bucket == b.id && one(aws_s3_bucket_ownership_controls.this[k].rule).object_ownership == "BucketOwnerEnforced"])
    error_message = "ACLs must be disabled on every bucket, so no object can be made public by ACL."
  }

  assert {
    condition = [for r in aws_s3_bucket_server_side_encryption_configuration.documents.rule : [
      one(r.apply_server_side_encryption_by_default).sse_algorithm,
      one(r.apply_server_side_encryption_by_default).kms_master_key_id,
      r.bucket_key_enabled,
    ]] == [["aws:kms", var.kms_key_arn, true]]
    error_message = "Documents must be encrypted with the platform's data key (with an S3 bucket key to cut KMS calls)."
  }

  assert {
    condition     = [for r in aws_s3_bucket_server_side_encryption_configuration.static.rule : one(r.apply_server_side_encryption_by_default).sse_algorithm] == ["AES256"]
    error_message = "Static assets must be encrypted at rest with S3-managed keys."
  }

  assert {
    condition     = aws_s3_bucket_server_side_encryption_configuration.documents.bucket == aws_s3_bucket.this["documents"].id && aws_s3_bucket_server_side_encryption_configuration.static.bucket == aws_s3_bucket.this["static"].id
    error_message = "Each encryption configuration must belong to its own bucket."
  }
}

run "documents_cors_allows_only_the_cloudfront_origin" {
  command = apply

  variables {
    documents_cors_allowed_origin = "https://d111111abcdef8.cloudfront.net"
  }

  assert {
    condition     = one(aws_s3_bucket_cors_configuration.documents).bucket == aws_s3_bucket.this["documents"].id
    error_message = "The CORS rule must be on the Documents bucket."
  }

  assert {
    condition     = length(one(aws_s3_bucket_cors_configuration.documents).cors_rule) == 1
    error_message = "There must be exactly one CORS rule."
  }

  assert {
    condition     = [for r in one(aws_s3_bucket_cors_configuration.documents).cors_rule : r.allowed_origins] == [toset(["https://d111111abcdef8.cloudfront.net"])]
    error_message = "The only allowed origin must be the CloudFront origin."
  }

  assert {
    condition     = [for r in one(aws_s3_bucket_cors_configuration.documents).cors_rule : r.allowed_methods] == [toset(["GET", "PUT"])]
    error_message = "Browsers may only upload (presigned PUT) and download (presigned GET)."
  }

  assert {
    condition     = alltrue([for r in one(aws_s3_bucket_cors_configuration.documents).cors_rule : !contains(r.allowed_headers, "*") && r.expose_headers == toset(["ETag"])])
    error_message = "Allowed headers must be listed explicitly, and only ETag exposed."
  }

  assert {
    condition     = output.documents_cors_allowed_origin == "https://d111111abcdef8.cloudfront.net"
    error_message = "The module must output the origin it allows."
  }
}

run "documents_allow_no_cross_origin_requests_until_the_origin_is_known" {
  command = plan

  assert {
    condition     = length(aws_s3_bucket_cors_configuration.documents) == 0 && output.documents_cors_allowed_origin == null
    error_message = "Without a CloudFront origin, the Documents bucket must have no CORS rule at all."
  }
}

run "rejects_a_wildcard_cors_origin" {
  command = plan

  variables {
    documents_cors_allowed_origin = "*"
  }

  expect_failures = [var.documents_cors_allowed_origin]
}

run "rejects_a_plain_http_cors_origin" {
  command = plan

  variables {
    documents_cors_allowed_origin = "http://d111111abcdef8.cloudfront.net"
  }

  expect_failures = [var.documents_cors_allowed_origin]
}

run "rejects_a_cors_origin_with_a_path" {
  command = plan

  variables {
    documents_cors_allowed_origin = "https://d111111abcdef8.cloudfront.net/"
  }

  expect_failures = [var.documents_cors_allowed_origin]
}

run "rejects_a_wildcard_subdomain_cors_origin" {
  command = plan

  variables {
    documents_cors_allowed_origin = "https://*.cloudfront.net"
  }

  expect_failures = [var.documents_cors_allowed_origin]
}

run "static_assets_are_readable_only_by_the_cloudfront_distribution" {
  command = apply

  variables {
    static_assets_distribution_arn = "arn:aws:cloudfront::123456789012:distribution/E2EXAMPLE12345"
  }

  assert {
    condition = [
      aws_cloudfront_origin_access_control.static.origin_access_control_origin_type,
      aws_cloudfront_origin_access_control.static.signing_behavior,
      aws_cloudfront_origin_access_control.static.signing_protocol,
    ] == ["s3", "always", "sigv4"]
    error_message = "Static assets must be fetched through an S3 origin access control that signs every request."
  }

  assert {
    condition     = output.static_origin_access_control_id == aws_cloudfront_origin_access_control.static.id
    error_message = "The module must output the origin access control for the cdn module."
  }

  assert {
    condition = jsondecode(aws_s3_bucket_policy.static.policy).Statement[1] == {
      Sid       = "AllowCloudFrontOriginAccessControlReads"
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.this["static"].arn}/*"
      Condition = { StringEquals = { "AWS:SourceArn" = "arn:aws:cloudfront::123456789012:distribution/E2EXAMPLE12345" } }
    }
    error_message = "Only the given CloudFront distribution may read static objects, and only with GetObject."
  }

  assert {
    condition     = length(jsondecode(aws_s3_bucket_policy.static.policy).Statement) == 2 && aws_s3_bucket_policy.static.bucket == aws_s3_bucket.this["static"].id
    error_message = "The static bucket policy must hold only the TLS rule and the CloudFront grant."
  }
}

run "static_assets_are_readable_by_no_one_until_the_distribution_is_known" {
  command = apply

  assert {
    condition     = length(jsondecode(aws_s3_bucket_policy.static.policy).Statement) == 1
    error_message = "Without a distribution ARN, the static bucket policy must grant nothing."
  }
}

run "every_bucket_refuses_requests_without_tls" {
  command = apply

  assert {
    condition = alltrue([for k, p in { documents = aws_s3_bucket_policy.documents, static = aws_s3_bucket_policy.static } :
      p.bucket == aws_s3_bucket.this[k].id &&
      jsondecode(p.policy).Statement[0] == {
        Sid       = "DenyRequestsWithoutTls"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [aws_s3_bucket.this[k].arn, "${aws_s3_bucket.this[k].arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      }
    ])
    error_message = "Every bucket must deny any request that does not use TLS."
  }

  assert {
    condition     = length(jsondecode(aws_s3_bucket_policy.documents.policy).Statement) == 1
    error_message = "The Documents bucket policy must grant nothing; task roles get access through IAM (ticket 09-04)."
  }
}

run "rejects_a_distribution_arn_that_is_not_cloudfront" {
  command = plan

  variables {
    static_assets_distribution_arn = "arn:aws:s3:::some-bucket"
  }

  expect_failures = [var.static_assets_distribution_arn]
}

run "abandoned_uploads_are_cleaned_up" {
  command = apply

  assert {
    condition = alltrue([for k, b in aws_s3_bucket.this :
      aws_s3_bucket_lifecycle_configuration.this[k].bucket == b.id &&
      [for r in aws_s3_bucket_lifecycle_configuration.this[k].rule : [r.status, one(r.abort_incomplete_multipart_upload).days_after_initiation]] == [["Enabled", 1]]
    ])
    error_message = "Every bucket must abort incomplete multipart uploads after a day, and expire nothing else."
  }
}

run "outputs_what_the_ecs_and_cdn_modules_need" {
  command = apply

  assert {
    condition     = output.documents_bucket_name == "studio-demo-documents-123456789012" && output.static_bucket_name == "studio-demo-static-123456789012"
    error_message = "Bucket names must be the prefix, the purpose and the account ID."
  }

  assert {
    condition     = output.documents_bucket_arn == aws_s3_bucket.this["documents"].arn && output.static_bucket_arn == aws_s3_bucket.this["static"].arn
    error_message = "The module must output both bucket ARNs for task role policies."
  }

  assert {
    condition     = output.static_bucket_regional_domain_name == aws_s3_bucket.this["static"].bucket_regional_domain_name
    error_message = "The module must output the static bucket's regional domain for the CloudFront origin."
  }
}

run "buckets_keep_their_objects_on_destroy_by_default" {
  command = plan

  assert {
    condition     = alltrue([for b in aws_s3_bucket.this : b.force_destroy == false])
    error_message = "Buckets must refuse to be destroyed while they hold objects, unless force_destroy is set."
  }
}

run "force_destroy_empties_buckets_on_destroy" {
  command = plan

  variables {
    force_destroy = true
  }

  assert {
    condition     = alltrue([for b in aws_s3_bucket.this : b.force_destroy])
    error_message = "force_destroy must reach every bucket."
  }
}

run "every_resource_carries_the_standard_tags" {
  command = plan

  assert {
    condition     = output.tags == { Environment = "demo", Project = "rag-agent-studio", Module = "storage", ManagedBy = "terraform" }
    error_message = "Tags must merge the caller's tags with the module's own."
  }

  assert {
    condition     = alltrue([for b in aws_s3_bucket.this : alltrue([for key, value in output.tags : lookup(b.tags, key, null) == value])])
    error_message = "Every bucket must carry the standard tags."
  }

  assert {
    condition     = output.name == "studio-demo-storage"
    error_message = "The storage name must be derived from name_prefix."
  }
}

run "rejects_a_key_that_is_not_a_kms_arn" {
  command = plan

  variables {
    kms_key_arn = "alias/aws/s3"
  }

  expect_failures = [var.kms_key_arn]
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
