"""Typed service settings, read from the environment and validated at startup."""

import base64
import binascii
from typing import Any, Literal
from urllib.parse import quote

from pydantic import (
    Field,
    HttpUrl,
    PostgresDsn,
    RedisDsn,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class SettingsError(RuntimeError):
    """Raised when the environment is missing a required setting or holds an invalid one."""


class Settings(BaseSettings):
    # An empty variable counts as unset, so `LOGFIRE_TOKEN=` in compose means "no token".
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore", env_ignore_empty=True)

    environment: Literal["local", "test", "demo", "production"] = "local"
    database_url: PostgresDsn
    redis_url: RedisDsn
    # In AWS the URLs arrive in parts: ECS injects the password and AUTH token from Secrets
    # Manager as their own variables (ticket 09-06). Unset DATABASE_URL or REDIS_URL is then
    # built from these; a whole URL always wins.
    database_host: str | None = None
    database_port: int = Field(default=5432, gt=0, lt=65536)
    database_name: str | None = None
    database_user: str | None = None
    database_password: SecretStr | None = None
    database_tls: bool = False
    redis_host: str | None = None
    redis_port: int = Field(default=6379, gt=0, lt=65536)
    redis_tls: bool = False
    redis_auth_token: SecretStr | None = None
    celery_task_always_eager: bool = False
    worker_health_timeout_seconds: float = Field(default=5.0, gt=0)
    # How long a Studio session lasts without signing in again.
    session_ttl_seconds: int = Field(default=14 * 24 * 60 * 60, gt=0)
    # Sign-in protection. Failed sign-ins are counted per account (email) and per IP address.
    # After `*_delay_after_failures` failures, each attempt waits `sign_in_delay_base_seconds`,
    # doubling per further failure up to `sign_in_delay_max_seconds`; after
    # `*_lockout_after_failures` failures, sign-in is locked for `sign_in_lockout_seconds`.
    # Counters are forgotten `sign_in_lockout_seconds` after the last failure.
    sign_in_account_delay_after_failures: int = Field(default=3, ge=0)
    sign_in_account_lockout_after_failures: int = Field(default=10, gt=0)
    sign_in_ip_delay_after_failures: int = Field(default=20, ge=0)
    sign_in_ip_lockout_after_failures: int = Field(default=100, gt=0)
    sign_in_delay_base_seconds: int = Field(default=1, gt=0)
    sign_in_delay_max_seconds: int = Field(default=30, gt=0)
    sign_in_lockout_seconds: int = Field(default=15 * 60, gt=0)
    # How long a password-checked sign-in waits for its MFA code.
    mfa_pending_ttl_seconds: int = Field(default=5 * 60, gt=0)
    # Wraps the data keys of envelope-encrypted secrets (TOTP secrets, Provider Credentials):
    # the local static-key wrapper (`docker compose`, tests) or AWS KMS (AWS).
    key_wrapper: Literal["local", "kms"] = "local"
    # The local wrapper's key: 32 random bytes, base64-encoded (`openssl rand -base64 32`).
    local_key_wrapper_key: SecretStr
    # The KMS key that wraps data keys, by ARN or alias; required when KEY_WRAPPER=kms.
    kms_key_id: str | None = None
    # KMS region; unset means boto3's default (AWS_REGION).
    kms_region: str | None = None
    # How Provider Credentials are checked when saved: a live call to the provider, or the
    # fake verifier (`docker compose`, tests), which passes every key except those starting
    # `fake-fail-<reason>`, which fail with that reason.
    credential_verifier: Literal["live", "fake"] = "live"
    # How long a live credential check waits for the provider.
    credential_check_timeout_seconds: float = Field(default=10.0, gt=0)
    # The platform's own AWS identity, which assumes Owners' Bedrock roles: the principal the
    # Studio puts in the trust policy Owners paste into AWS. In AWS it is the API's task role;
    # `docker compose` has no AWS identity, so the default is a placeholder.
    bedrock_platform_principal: str = "arn:aws:iam::000000000000:role/rag-agent-studio-local"
    # The region whose STS endpoint assumes Owners' roles and checks access keys.
    bedrock_sts_region: str = "us-east-1"
    # Assumed-role sessions are reused until this long before they expire.
    bedrock_session_refresh_seconds: int = Field(default=5 * 60, ge=0)
    # Which adapters the model gateway builds chat models, embedders and rerankers with: the
    # providers' real clients, or the offline fakes (`docker compose`, tests).
    model_gateway: Literal["live", "fake"] = "live"
    # How long a call to a model provider may take.
    model_timeout_seconds: float = Field(default=120.0, gt=0)
    # How long a password reset link works.
    password_reset_ttl_seconds: int = Field(default=60 * 60, gt=0)
    # How long an invite link works.
    invite_ttl_seconds: int = Field(default=7 * 24 * 60 * 60, gt=0)
    # The Studio's public address; links in emails point here.
    studio_url: HttpUrl = HttpUrl("http://localhost:5173")
    # Which mailer adapter sends email: in-memory outbox (tests), SMTP (Mailpit) or AWS SES.
    mailer: Literal["outbox", "smtp", "ses"] = "outbox"
    mail_from: str = "RAG Agent Studio <no-reply@rag-agent-studio.invalid>"
    smtp_host: str = "localhost"
    smtp_port: int = Field(default=1025, gt=0, lt=65536)
    smtp_timeout_seconds: float = Field(default=10.0, gt=0)
    # SES region; unset means boto3's default (AWS_REGION).
    ses_region: str | None = None
    # Where uploaded files and converted markdown are kept: S3 (or RustFS, the same adapter with
    # another endpoint) or the in-memory fake (tests).
    object_store: Literal["s3", "memory"] = "s3"
    object_store_bucket: str = "studio-documents"
    # Create the bucket at startup if it's missing (RustFS starts empty). AWS buckets are
    # created by Terraform, so this stays off there.
    object_store_create_bucket: bool = False
    # The S3 endpoint the API and worker use; unset means AWS S3. RustFS: http://rustfs:9000.
    object_store_endpoint_url: HttpUrl | None = None
    # The endpoint browsers upload to through presigned URLs; unset means the one above.
    object_store_public_endpoint_url: HttpUrl | None = None
    object_store_region: str = "us-east-1"
    # Static keys (RustFS); unset means boto3's default credential chain (an AWS role).
    object_store_access_key_id: str | None = None
    object_store_secret_access_key: SecretStr | None = None
    # How long a presigned upload URL works.
    upload_url_ttl_seconds: int = Field(default=15 * 60, gt=0)
    # How long a presigned download URL for a Document's original file works.
    download_url_ttl_seconds: int = Field(default=5 * 60, gt=0)
    # The largest file a Document can be uploaded from.
    max_upload_bytes: int = Field(default=50 * 1024 * 1024, gt=0)
    # The largest logo or default Agent avatar image a Theme can have.
    max_theme_image_bytes: int = Field(default=1024 * 1024, gt=0)
    # Converts uploaded files to markdown and structure: Docling, or the fake (tests).
    document_converter: Literal["docling", "fake"] = "docling"
    # Embeds Chunks for the local Embedding Model: fastembed's multilingual-e5-small, or the
    # deterministic hash-based fake (tests, and stacks that can't download the model).
    embedder: Literal["local", "fake"] = "local"
    # Scans Chunks for instructions aimed at an AI during ingestion: the heuristic baseline, or
    # the rule-driven fake (tests). Spec 08 adds the local ONNX classifier.
    injection_classifier: Literal["heuristic", "fake"] = "heuristic"
    # Checks every Visitor message before the model sees it (the input Guardrail): the local
    # ONNX prompt-injection model (bundled in the API image), the heuristic patterns (stacks
    # built without the model), or the rule-driven fake (tests).
    input_classifier: Literal["local", "heuristic", "fake"] = "local"
    # The local model's score, from 0 to 1, at or above which a message is flagged.
    input_classifier_threshold: float = Field(default=0.5, gt=0, le=1)
    # The largest Chunk, in the Embedding Model's tokens; capped at the model's own limit.
    chunk_max_tokens: int = Field(default=256, gt=0)
    # Transient ingestion failures (the Embedding Model's provider failing) are retried
    # automatically, up to this many attempts in all, waiting longer after each one: the base
    # delay, doubled per attempt, never more than the maximum.
    ingestion_max_attempts: int = Field(default=4, ge=1)
    ingestion_retry_base_seconds: float = Field(default=10.0, gt=0)
    ingestion_retry_max_seconds: float = Field(default=300.0, gt=0)
    # How many Chunks a re-embed job embeds and writes at a time; each batch shows as progress.
    # Provider failures during a re-embed are retried like ingestion's.
    re_embed_batch_size: int = Field(default=64, gt=0)
    # Traces go to Logfire when a token is set, and to the console as JSON otherwise.
    logfire_token: SecretStr | None = None
    # Only needed for a self-hosted Logfire; otherwise the region is read from the token.
    logfire_base_url: HttpUrl | None = None

    @model_validator(mode="before")
    @classmethod
    def _urls_from_parts(cls, data: dict[str, Any]) -> dict[str, Any]:
        # Runs on the raw values from the environment, before any are parsed.
        if not data.get("database_url") and data.get("database_host"):
            if not (data.get("database_name") and data.get("database_user")):
                raise ValueError(
                    "DATABASE_HOST is set, so DATABASE_NAME and DATABASE_USER are required"
                )
            data["database_url"] = _url(
                "postgresql+asyncpg",
                _credentials(data["database_user"], data.get("database_password")),
                data["database_host"],
                data.get("database_port", 5432),
                data["database_name"],
                "ssl=require" if _true(data.get("database_tls")) else "",
            )
        if not data.get("redis_url") and data.get("redis_host"):
            tls = _true(data.get("redis_tls"))
            data["redis_url"] = _url(
                "rediss" if tls else "redis",
                _credentials("", data.get("redis_auth_token")),
                data["redis_host"],
                data.get("redis_port", 6379),
                "0",
                # redis-py and Celery both refuse a rediss:// URL that does not say how to verify.
                "ssl_cert_reqs=required" if tls else "",
            )
        return data

    @field_validator("local_key_wrapper_key")
    @classmethod
    def _is_a_32_byte_key(cls, value: SecretStr) -> SecretStr:
        try:
            key = base64.b64decode(value.get_secret_value(), validate=True)
        except binascii.Error:
            key = b""
        if len(key) != 32:
            raise ValueError("must be 32 bytes, base64-encoded")
        return value

    @model_validator(mode="after")
    def _kms_has_a_key(self) -> "Settings":
        if self.key_wrapper == "kms" and not self.kms_key_id:
            raise ValueError("KMS_KEY_ID is required when KEY_WRAPPER is kms")
        return self


def _true(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _credentials(user: str, secret: Any) -> str:
    if secret is None:
        return f"{quote(user, safe='')}@" if user else ""
    return f"{quote(user, safe='')}:{quote(str(secret), safe='')}@"


def _url(scheme: str, credentials: str, host: str, port: Any, path: str, query: str) -> str:
    return f"{scheme}://{credentials}{host}:{port}/{path}" + (f"?{query}" if query else "")


def load_settings() -> Settings:
    """Load settings, turning validation failures into one readable message."""
    try:
        return Settings()  # values come from the environment
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']).upper()}: {error['msg']}"
            for error in exc.errors()
        )
        raise SettingsError(f"Invalid service settings. {problems}") from None
