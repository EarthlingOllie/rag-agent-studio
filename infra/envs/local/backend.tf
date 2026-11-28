# The rehearsal (spec 23) keeps its state in a bucket inside the emulator, with S3 native locking as the demo does.
# scripts/deploy/rehearse.sh creates the bucket and passes its name and region at init time, through deploy.sh, as the
# demo's deploy does. The endpoint is pinned to Floci as terraform sees it (on the rehearsal's tools network), so no
# init anywhere can read or write this state at AWS, whatever credentials the machine holds. The emulator serves
# buckets by path and has no credentials or account to check, hence the four settings after it; encrypt and kms_key_id
# stay unset as in the demo.
terraform {
  backend "s3" {
    key                         = "envs/local/terraform.tfstate"
    use_lockfile                = true
    endpoints                   = { s3 = "http://floci:4566" }
    use_path_style              = true
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_requesting_account_id  = true
  }
}
