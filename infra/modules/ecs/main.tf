# Stub module (ticket 01-02). Spec 09 replaces this with the real ECS Fargate cluster and services for the API, worker, Beat and Studio.
# It already has the shared input contract so that fmt, validate, tflint, checkov and terraform test run from slice 1.
locals {
  module_name = "ecs"
  name        = "${var.name_prefix}-${local.module_name}"
  tags        = merge(var.tags, { Module = local.module_name, ManagedBy = "terraform" })
}
