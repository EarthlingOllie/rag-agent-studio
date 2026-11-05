# Stub module (ticket 01-02). Spec 09 replaces this with the real CloudFront distribution in front of the ALB and Studio assets.
# It already has the shared input contract so that fmt, validate, tflint, checkov and terraform test run from slice 1.
locals {
  module_name = "cdn"
  name        = "${var.name_prefix}-${local.module_name}"
  tags        = merge(var.tags, { Module = local.module_name, ManagedBy = "terraform" })
}
