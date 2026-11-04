# Provider Credentials stored in Postgres with KMS envelope encryption

Provider Credential secrets are encrypted with a per-record data key, which is itself wrapped by an AWS KMS key; locally, a static key file stands in for KMS. The ciphertext is stored in Postgres. Secrets are write-only through the API: once saved, only a masked suffix is ever returned. We preferred this to one AWS Secrets Manager secret per credential because it keeps credentials transactional with the rest of the Organisation's data, costs nothing per secret, and runs the same way locally.

Bedrock credentials can be a cross-account IAM role ARN plus an external ID, which the platform assumes so no secret is stored; this is the preferred option. Access keys are also accepted, because local environments can't assume roles. Every credential is checked with a live call when saved.
