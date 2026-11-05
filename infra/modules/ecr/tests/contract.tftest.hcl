# Module contract for the ecr module (ticket 09-04), at the module seam, with a mocked AWS provider.
# Nothing here calls AWS.
mock_provider "aws" {}

variables {
  name_prefix      = "studio-demo"
  tags             = { Environment = "demo", Project = "rag-agent-studio" }
  repository_names = ["rag-agent-studio/api", "rag-agent-studio/studio"]
  kms_key_arn      = "arn:aws:kms:eu-west-2:123456789012:key/11111111-2222-3333-4444-555555555555"
}

run "scans_every_image_on_push" {
  command = plan

  assert {
    condition     = keys(aws_ecr_repository.this) == ["rag-agent-studio/api", "rag-agent-studio/studio"]
    error_message = "There must be one repository per listed name."
  }

  assert {
    condition     = alltrue([for r in aws_ecr_repository.this : length(r.image_scanning_configuration) == 1 && r.image_scanning_configuration[0].scan_on_push])
    error_message = "Every repository must scan images on push."
  }
}

run "expires_untagged_and_old_images" {
  command = plan

  assert {
    condition     = keys(aws_ecr_lifecycle_policy.this) == ["rag-agent-studio/api", "rag-agent-studio/studio"]
    error_message = "Every repository must have a lifecycle policy."
  }

  assert {
    condition = alltrue([for name, p in aws_ecr_lifecycle_policy.this : p.repository == name && jsondecode(p.policy) == {
      rules = [
        {
          rulePriority = 1
          description  = "Expire untagged images after 7 days"
          selection    = { tagStatus = "untagged", countType = "sinceImagePushed", countUnit = "days", countNumber = 7 }
          action       = { type = "expire" }
        },
        {
          rulePriority = 2
          description  = "Keep the newest 20 tagged images"
          selection    = { tagStatus = "tagged", tagPatternList = ["*"], countType = "imageCountMoreThan", countNumber = 20 }
          action       = { type = "expire" }
        },
      ]
    }])
    error_message = "The lifecycle policy must expire untagged images after a week and keep the newest 20 tagged images."
  }
}

run "lifecycle_limits_are_configurable" {
  command = plan

  variables {
    keep_tagged_images   = 5
    untagged_expiry_days = 1
  }

  assert {
    condition = alltrue([for p in aws_ecr_lifecycle_policy.this :
      jsondecode(p.policy).rules[0].selection.countNumber == 1 && jsondecode(p.policy).rules[1].selection.countNumber == 5
    ])
    error_message = "keep_tagged_images and untagged_expiry_days must reach the lifecycle policy."
  }
}

run "tags_are_immutable_and_images_encrypted_with_the_data_key" {
  command = plan

  assert {
    condition     = alltrue([for r in aws_ecr_repository.this : r.image_tag_mutability == "IMMUTABLE"])
    error_message = "A pushed tag must never be overwritten, so a deployed tag always names the image that was scanned."
  }

  assert {
    condition     = alltrue([for r in aws_ecr_repository.this : r.encryption_configuration[0].encryption_type == "KMS" && r.encryption_configuration[0].kms_key == var.kms_key_arn])
    error_message = "Images must be encrypted with the data key."
  }

  assert {
    condition     = alltrue([for r in aws_ecr_repository.this : r.force_delete == false])
    error_message = "Repositories holding images must not be deleted unless asked."
  }
}

run "force_delete_lets_one_destroy_remove_everything" {
  command = plan

  variables {
    force_delete = true
  }

  assert {
    condition     = alltrue([for r in aws_ecr_repository.this : r.force_delete])
    error_message = "force_delete must reach every repository."
  }
}

run "outputs_each_repository_url_and_arn" {
  command = apply

  assert {
    condition     = output.repository_urls == { for k, r in aws_ecr_repository.this : k => r.repository_url }
    error_message = "The module must output each repository URL, keyed by name."
  }

  assert {
    condition     = output.repository_arns == { for k, r in aws_ecr_repository.this : k => r.arn }
    error_message = "The module must output each repository ARN, keyed by name."
  }
}

run "every_resource_carries_the_standard_tags" {
  command = plan

  assert {
    condition     = output.tags == { Environment = "demo", Project = "rag-agent-studio", Module = "ecr", ManagedBy = "terraform" }
    error_message = "Tags must merge the caller's tags with the module's own."
  }

  assert {
    condition     = alltrue([for r in aws_ecr_repository.this : alltrue([for key, value in output.tags : lookup(r.tags, key, null) == value])])
    error_message = "Every repository must carry the standard tags."
  }

  assert {
    condition     = output.name == "studio-demo-ecr"
    error_message = "The ecr name must be derived from name_prefix."
  }
}

run "rejects_no_repositories" {
  command = plan

  variables {
    repository_names = []
  }

  expect_failures = [var.repository_names]
}

run "rejects_an_uppercase_repository_name" {
  command = plan

  variables {
    repository_names = ["Rag-Agent-Studio/API"]
  }

  expect_failures = [var.repository_names]
}

run "rejects_keeping_no_tagged_images" {
  command = plan

  variables {
    keep_tagged_images = 0
  }

  expect_failures = [var.keep_tagged_images]
}

run "rejects_a_fractional_untagged_expiry" {
  command = plan

  variables {
    untagged_expiry_days = 0.5
  }

  expect_failures = [var.untagged_expiry_days]
}

run "rejects_a_key_that_is_not_a_kms_arn" {
  command = plan

  variables {
    kms_key_arn = "alias/aws/ecr"
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
