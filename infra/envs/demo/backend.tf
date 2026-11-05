# State lives in the bucket the bootstrap creates (infra/bootstrap), with S3 native locking: Terraform writes a
# .tflock object next to the state, so no DynamoDB table is needed. bucket and region come from the bootstrap's
# backend_config output at init time; see docs/infra-bootstrap.md. encrypt and kms_key_id are deliberately unset:
# the bucket's default encryption (its own KMS key) then applies, whereas encrypt = true without a key would ask S3
# for SSE-S3 instead.
terraform {
  backend "s3" {
    key          = "envs/demo/terraform.tfstate"
    use_lockfile = true
  }
}
