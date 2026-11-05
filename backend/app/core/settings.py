"""Typed service settings, read from the environment and validated at startup."""

from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class SettingsError(RuntimeError):
    """Raised when the environment is missing a required setting or holds an invalid one."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    environment: Literal["local", "test", "demo", "production"] = "local"
    database_url: PostgresDsn
    redis_url: RedisDsn
    celery_task_always_eager: bool = False
    worker_health_timeout_seconds: float = Field(default=5.0, gt=0)


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
