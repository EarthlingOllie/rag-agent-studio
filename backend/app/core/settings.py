"""Typed service settings, read from the environment and validated at startup."""

from typing import Literal

from pydantic import Field, HttpUrl, PostgresDsn, RedisDsn, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class SettingsError(RuntimeError):
    """Raised when the environment is missing a required setting or holds an invalid one."""


class Settings(BaseSettings):
    # An empty variable counts as unset, so `LOGFIRE_TOKEN=` in compose means "no token".
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore", env_ignore_empty=True)

    environment: Literal["local", "test", "demo", "production"] = "local"
    database_url: PostgresDsn
    redis_url: RedisDsn
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
    # How long a password reset link works.
    password_reset_ttl_seconds: int = Field(default=60 * 60, gt=0)
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
    # Traces go to Logfire when a token is set, and to the console as JSON otherwise.
    logfire_token: SecretStr | None = None
    # Only needed for a self-hosted Logfire; otherwise the region is read from the token.
    logfire_base_url: HttpUrl | None = None


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
