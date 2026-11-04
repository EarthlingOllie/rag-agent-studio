# Provider Credentials stored in Postgres with KMS envelope encryption

Provider Credential secrets are encrypted with a per-record data key, which is itself wrapped by an AWS KMS key; locally, a static key file stands in for KMS. The ciphertext is stored in Postgres. Secrets are write-only through the API: once saved, only a masked suffix is ever returned. We preferred this to one AWS Secrets Manager secret per credential because it keeps credentials transactional with the rest of the Organisation's data, costs nothing per secret, and runs the same way locally.
