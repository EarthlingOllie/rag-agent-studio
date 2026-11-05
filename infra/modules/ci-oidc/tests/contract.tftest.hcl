# Module contract for ci-oidc: the GitHub Actions OIDC provider and the deploy role trust only one repository.
mock_provider "aws" {
  override_during = plan

  mock_resource "aws_iam_openid_connect_provider" {
    defaults = { arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com" }
  }

  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/studio-demo-github-deploy" }
  }
}

variables {
  name_prefix       = "studio-demo"
  tags              = { Environment = "demo" }
  github_repository = "EarthlingOllie/rag-agent-studio"
}

run "names_resources_from_the_prefix" {
  command = plan

  assert {
    condition     = output.name == "studio-demo-ci-oidc"
    error_message = "The ci-oidc name must be derived from name_prefix."
  }

  assert {
    condition     = output.tags == { Environment = "demo", Module = "ci-oidc", ManagedBy = "terraform" }
    error_message = "Tags must merge the caller's tags with the module's own."
  }

  assert {
    condition     = aws_iam_role.deploy.name == "studio-demo-github-deploy"
    error_message = "The deploy role must be named from name_prefix."
  }

  assert {
    condition     = aws_iam_role.deploy.tags == tomap({ Environment = "demo", Module = "ci-oidc", ManagedBy = "terraform" })
    error_message = "The deploy role must carry the module's tags."
  }
}

run "creates_the_github_oidc_provider" {
  command = plan

  assert {
    condition     = aws_iam_openid_connect_provider.github[0].url == "https://token.actions.githubusercontent.com"
    error_message = "The provider must be GitHub Actions' token issuer."
  }

  assert {
    condition     = aws_iam_openid_connect_provider.github[0].client_id_list == toset(["sts.amazonaws.com"])
    error_message = "The provider must only accept the STS audience."
  }
}

run "trusts_only_this_repository" {
  command = plan

  assert {
    condition     = length(output.trust_policy.Statement) == 1
    error_message = "The trust policy must have exactly one statement."
  }

  assert {
    condition     = output.trust_policy.Statement[0].Action == "sts:AssumeRoleWithWebIdentity"
    error_message = "The role must only be assumable with a web identity token."
  }

  assert {
    condition     = output.trust_policy.Statement[0].Condition.StringEquals == { "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com" }
    error_message = "The token's audience must be STS."
  }

  assert {
    condition = output.trust_policy.Statement[0].Condition.StringLike == {
      "token.actions.githubusercontent.com:sub" = [
        "repo:EarthlingOllie/rag-agent-studio:ref:refs/heads/*",
        "repo:EarthlingOllie/rag-agent-studio:pull_request",
        "repo:EarthlingOllie/rag-agent-studio:environment:*",
      ]
    }
    error_message = "Only this repository's branches, pull requests and environments may assume the role."
  }

  assert {
    condition     = output.trust_policy.Statement[0].Principal == { Federated = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com" }
    error_message = "The role must federate only with the GitHub OIDC provider this module creates."
  }

  assert {
    condition     = output.role_arn == "arn:aws:iam::123456789012:role/studio-demo-github-deploy"
    error_message = "The module must output the deploy role's ARN."
  }

  assert {
    condition     = jsondecode(aws_iam_role.deploy.assume_role_policy) == output.trust_policy
    error_message = "The role must use the asserted trust policy."
  }
}

run "narrows_trust_to_chosen_subjects" {
  command = plan

  variables {
    subject_claims = ["ref:refs/heads/main"]
  }

  assert {
    condition = output.trust_policy.Statement[0].Condition.StringLike == {
      "token.actions.githubusercontent.com:sub" = ["repo:EarthlingOllie/rag-agent-studio:ref:refs/heads/main"]
    }
    error_message = "The trust must list exactly the chosen subjects."
  }
}

run "reuses_an_existing_oidc_provider" {
  command = plan

  variables {
    existing_oidc_provider_arn = "arn:aws:iam::210987654321:oidc-provider/token.actions.githubusercontent.com"
  }

  assert {
    condition     = length(aws_iam_openid_connect_provider.github) == 0
    error_message = "No second GitHub provider may be created when one exists."
  }

  assert {
    condition     = output.trust_policy.Statement[0].Principal.Federated == "arn:aws:iam::210987654321:oidc-provider/token.actions.githubusercontent.com"
    error_message = "The trust must federate with the existing provider."
  }

  assert {
    condition     = output.oidc_provider_arn == "arn:aws:iam::210987654321:oidc-provider/token.actions.githubusercontent.com"
    error_message = "The module must output the provider it trusts."
  }
}

run "attaches_the_chosen_managed_policies" {
  command = plan

  variables {
    managed_policy_arns = ["arn:aws:iam::aws:policy/PowerUserAccess"]
  }

  assert {
    condition     = aws_iam_role_policy_attachment.managed["arn:aws:iam::aws:policy/PowerUserAccess"].role == "studio-demo-github-deploy"
    error_message = "Each managed policy must be attached to the deploy role."
  }
}

run "attaches_no_inline_policy_by_default" {
  command = plan

  assert {
    condition     = length(aws_iam_role_policy.inline) == 0
    error_message = "Without a policy document the role has no inline policy."
  }

  assert {
    condition     = length(aws_iam_role_policy_attachment.managed) == 0
    error_message = "Without managed policies nothing is attached."
  }
}

run "attaches_the_inline_policy" {
  command = plan

  variables {
    inline_policy_json = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "s3:ListBucket", Resource = "arn:aws:s3:::state" }] })
  }

  assert {
    condition     = jsondecode(aws_iam_role_policy.inline[0].policy).Statement[0].Resource == "arn:aws:s3:::state"
    error_message = "The inline policy must be the one passed in."
  }
}

run "rejects_an_invalid_prefix" {
  command = plan

  variables {
    name_prefix = "Studio_Demo"
  }

  expect_failures = [var.name_prefix]
}

run "rejects_a_wildcard_repository" {
  command = plan

  variables {
    github_repository = "EarthlingOllie/*"
  }

  expect_failures = [var.github_repository]
}

run "rejects_a_wildcard_subject" {
  command = plan

  variables {
    subject_claims = ["*"]
  }

  expect_failures = [var.subject_claims]
}
