# GitHub Actions OIDC provider and the deploy role CI assumes. The trust policy accepts tokens from one repository only,
# so no long-lived AWS keys are stored in GitHub (spec 09, user story 29).
locals {
  module_name = "ci-oidc"
  name        = "${var.name_prefix}-${local.module_name}"
  tags        = merge(var.tags, { Module = local.module_name, ManagedBy = "terraform" })

  issuer_host       = "token.actions.githubusercontent.com"
  create_provider   = var.existing_oidc_provider_arn == null
  oidc_provider_arn = local.create_provider ? aws_iam_openid_connect_provider.github[0].arn : var.existing_oidc_provider_arn

  trust_policy = {
    Version = "2012-10-17"
    Statement = [{
      Sid       = "GitHubActionsThisRepositoryOnly"
      Effect    = "Allow"
      Action    = "sts:AssumeRoleWithWebIdentity"
      Principal = { Federated = local.oidc_provider_arn }
      Condition = {
        StringEquals = { "${local.issuer_host}:aud" = "sts.amazonaws.com" }
        StringLike   = { "${local.issuer_host}:sub" = [for claim in var.subject_claims : "repo:${var.github_repository}:${claim}"] }
      }
    }]
  }
}

resource "aws_iam_openid_connect_provider" "github" {
  count = local.create_provider ? 1 : 0

  url            = "https://${local.issuer_host}"
  client_id_list = ["sts.amazonaws.com"]
  tags           = local.tags
}

resource "aws_iam_role" "deploy" {
  name                 = "${var.name_prefix}-github-deploy"
  description          = "Assumed by GitHub Actions in ${var.github_repository} through OIDC."
  assume_role_policy   = jsonencode(local.trust_policy)
  max_session_duration = 3600
  tags                 = local.tags
}

resource "aws_iam_role_policy_attachment" "managed" {
  for_each = toset(var.managed_policy_arns)

  role       = aws_iam_role.deploy.name
  policy_arn = each.value
}

resource "aws_iam_role_policy" "inline" {
  count = var.inline_policy_json == null ? 0 : 1

  name   = "${var.name_prefix}-github-deploy"
  role   = aws_iam_role.deploy.id
  policy = var.inline_policy_json
}
