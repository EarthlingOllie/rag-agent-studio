# AWS bootstrap: state bucket and CI deploy role

`infra/bootstrap` is a root module applied **once, by hand**, before any environment. It creates:

- **The Terraform state bucket** `rag-agent-studio-tfstate-<account id>`: versioned (old versions expire after 90 days), encrypted with its own KMS key (rotation on, S3 bucket key on), every public access block on, ACLs disabled, and a bucket policy that denies requests without TLS. The bucket and key have `prevent_destroy`.
- **The GitHub OIDC provider and deploy role** (`infra/modules/ci-oidc`), `rag-agent-studio-github-deploy`. The role trusts tokens from `token.actions.githubusercontent.com` with audience `sts.amazonaws.com` and a subject of `repo:EarthlingOllie/rag-agent-studio:` followed by `ref:refs/heads/*`, `pull_request` or `environment:*`. No other repository can assume it, and no long-lived AWS keys are stored in GitHub.

The deploy role gets `PowerUserAccess` (every service except IAM), plus an inline policy that lets it:

- use the state bucket, its lock files and the state key;
- manage IAM roles and policies whose names start with `studio-` (each environment's task roles), and nothing else in IAM, including itself;
- not delete, re-policy, unversion or decrypt-disable the state bucket or its key (an explicit deny).

Environments keep their state in that bucket through the S3 backend with **native locking** (`use_lockfile = true` in `infra/envs/<env>/backend.tf`). Terraform writes `<key>.tflock` next to the state with a conditional put, so a second run fails with `Error acquiring the state lock` instead of corrupting state. No DynamoDB table is needed. The backend sets neither `encrypt` nor `kms_key_id`, so every state object gets the bucket's default KMS encryption.

## Steps

You need an AWS account, credentials for an administrator in it (for example `aws sso login`), and Terraform 1.10 or later (`scripts/ci/install-tools.sh terraform` installs the pinned 1.13.4).

1. **Apply the bootstrap.**

   ```sh
   cd infra/bootstrap
   terraform init
   terraform plan -out bootstrap.tfplan     # review: 1 KMS key + alias, 1 bucket and its 6 settings, OIDC provider, role, policies
   terraform apply bootstrap.tfplan
   ```

   Variables (all have defaults): `aws_region` (`eu-west-2`), `name_prefix` (`rag-agent-studio`), `github_repository` (`EarthlingOllie/rag-agent-studio`), `deploy_managed_policy_arns` (`PowerUserAccess`) and `managed_resource_prefix` (`studio-`). If the account already has a GitHub OIDC provider (an account can hold only one per URL), pass `-var existing_oidc_provider_arn=arn:aws:iam::<account>:oidc-provider/token.actions.githubusercontent.com` so it is reused.

2. **Configure the repository** (GitHub, Settings, Secrets and variables, Actions), from `terraform output`:

   | Name | Kind | Value |
   |---|---|---|
   | `AWS_DEPLOY_ROLE_ARN` | secret | `deploy_role_arn` |
   | `TF_STATE_BUCKET` | variable | `state_bucket_name` |
   | `AWS_REGION` | variable | `backend_config.region` (optional; workflows default to `eu-west-2`) |

   From then on, pull requests that touch `infra/` or `.github/workflows/infra.yml` get a `terraform plan` of `envs/demo` posted as a comment. Until the secret exists, the plan job is skipped and CI stays green. Setting the secret without `TF_STATE_BUCKET` fails `plan-gate` with an error naming the missing variable.

3. **Initialise an environment locally** (optional; CI does this itself):

   ```sh
   cd infra/envs/demo
   terraform init -backend-config="bucket=$(terraform -chdir=../../bootstrap output -raw state_bucket_name)" -backend-config="region=eu-west-2"
   ```

4. **Keep the bootstrap state.** The bootstrap's own state is local (`infra/bootstrap/terraform.tfstate`, ignored by git) because its bucket does not exist until it is applied. Keep that file somewhere safe (for example a password manager), or move it into the bucket: add `backend "s3" { key = "bootstrap/terraform.tfstate", use_lockfile = true }` to `infra/bootstrap/versions.tf` and run `terraform init -migrate-state -backend-config="bucket=<state_bucket_name>" -backend-config="region=<region>"`.

## Tearing down

Destroy every environment first (the `destroy` workflow; see [deploy-demo.md](deploy-demo.md#destroy-stop-paying)). The bootstrap's bucket and key have `prevent_destroy`, so removing them is deliberate: delete the `lifecycle` blocks, empty the bucket (every object version), then `terraform destroy` in `infra/bootstrap`. The KMS key is scheduled for deletion after 30 days.

## Cost

A KMS key is about 1 USD a month, plus request charges that the S3 bucket key keeps small. The state objects cost well under 0.01 USD a month. The OIDC provider and role are free.
