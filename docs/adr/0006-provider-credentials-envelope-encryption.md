# Provider Credentials stored in Postgres with KMS envelope encryption

Provider Credential secrets are encrypted with a per-record data key, which is itself wrapped by an AWS KMS key; locally, a static key from the `LOCAL_KEY_WRAPPER_KEY` setting stands in for KMS (amended by ticket 01-11: an environment setting rather than a key file, matching every other setting). The ciphertext is stored in Postgres. Secrets are write-only through the API: once saved, only a masked suffix is ever returned. We preferred this to one AWS Secrets Manager secret per credential because it keeps credentials transactional with the rest of the Organisation's data, costs nothing per secret, and runs the same way locally.

Bedrock credentials can be a cross-account IAM role ARN plus an external ID, which the platform assumes so no secret is stored; this is the preferred option. Access keys are also accepted, because local environments can't assume roles. Every credential is checked with a live call when saved.

The same envelope-encryption module (`backend/app/crypto/`) also stores Members' TOTP secrets (ticket 01-11). Each sealed record is self-describing: a format version (version 1 means AES-256-GCM with a 256-bit data key), the wrapping key's ID and the wrapped data key, so the algorithm or the wrapping key can be changed later without rewriting old records first.
