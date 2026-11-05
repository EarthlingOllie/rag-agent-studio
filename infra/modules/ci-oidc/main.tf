# Stub module (ticket 01-02). Spec 09 replaces this with the real GitHub Actions OIDC provider and deploy role.
# It already has the shared input contract so that fmt, validate, tflint, checkov and terraform test run from slice 1.
locals {
  module_name = "ci-oidc"
  name        = "${var.name_prefix}-${local.module_name}"
  tags        = merge(var.tags, { Module = local.module_name, ManagedBy = "terraform" })
}
