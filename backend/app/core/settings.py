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
