"""Every ECS container the ecs module defines starts with valid settings (ticket 09-06).

``infra/modules/ecs/tests/task-settings.json`` records the environment and secret names each
container gets in AWS; the module's ``terraform test`` run
``task_settings_match_the_recorded_contract`` pins the module to it. Here each container's
environment, with sample secret values in the shapes Terraform writes them, is loaded into the
backend's settings and the clients built from them.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from celery import Celery
from celery.backends.redis import RedisBackend
from redis import Redis
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.settings import Settings, load_settings

CONTRACT = Path(__file__).resolve().parents[3] / "infra/modules/ecs/tests/task-settings.json"
# Secret values in the shapes the Terraform modules generate them, plus characters a
# password could hold that must be escaped in a URL.
SECRET_VALUES = {
    "DATABASE_PASSWORD": "0f1e2d3c4b5a69788796a5b4c3d2e1f0/+:@?#",
    "REDIS_AUTH_TOKEN": "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f9",
    "SESSION_SECRET": "00112233445566778899aabbccddeeff00112233445566778899aabbccddeef",
    # 43 hex digits and a padding character: how the ecs module writes this key.
    "LOCAL_KEY_WRAPPER_KEY": "0123456789abcdef0123456789abcdef0123456789a=",
}


def _containers() -> dict[str, Any]:
    contract: dict[str, Any] = json.loads(CONTRACT.read_text())
    return {name: spec for name, spec in contract.items() if not name.startswith("_")}


def _use_task_env(container: str, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Exactly the environment ECS gives one container: nothing else from this machine."""
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)
    spec = _containers()[container]
    env = dict(spec["environment"]) | {name: SECRET_VALUES[name] for name in spec["secrets"]}
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return env


@pytest.fixture(params=sorted(_containers()))
def task_env(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    return _use_task_env(request.param, monkeypatch)


def test_the_contract_names_the_api_worker_beat_and_migration_containers() -> None:
    assert sorted(_containers()) == ["api", "beat", "migrate", "worker"]


def test_each_container_loads_settings_that_reach_rds_and_elasticache_over_tls(
    task_env: dict[str, str],
) -> None:
    settings = load_settings()

    assert settings.environment == "demo"
    assert settings.database_url.hosts()[0]["host"] == task_env["DATABASE_HOST"]
    assert "ssl=require" in str(settings.database_url)
    assert str(settings.redis_url).startswith("rediss://")
    assert settings.redis_url.host == task_env["REDIS_HOST"]


def test_each_container_can_build_its_database_and_redis_clients(
    task_env: dict[str, str],
) -> None:
    settings = load_settings()

    engine = create_async_engine(str(settings.database_url))
    assert engine.url.password == task_env.get("DATABASE_PASSWORD")
    assert engine.url.query == {"ssl": "require"}
    redis = Redis.from_url(str(settings.redis_url))
    assert redis.connection_pool.connection_kwargs.get("password") == task_env.get(
        "REDIS_AUTH_TOKEN"
    )
    # Celery refuses to build a rediss:// result backend that does not say how to verify
    # certificates (ValueError).
    celery = Celery(broker=str(settings.redis_url), backend=str(settings.redis_url))
    assert isinstance(celery.backend, RedisBackend)


@pytest.mark.parametrize("container", ["api", "worker"])
def test_the_api_and_worker_seal_with_kms_and_keep_documents_in_the_bucket(
    container: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_env = _use_task_env(container, monkeypatch)
    settings = load_settings()

    assert settings.key_wrapper == "kms"
    assert settings.kms_key_id == task_env["KMS_KEY_ID"]
    assert settings.object_store == "s3"
    assert settings.object_store_bucket == task_env["OBJECT_STORE_BUCKET"]
    assert settings.object_store_endpoint_url is None
    assert str(settings.studio_url).rstrip("/") == task_env["STUDIO_URL"]


def test_the_api_is_told_its_own_bedrock_trust_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    task_env = _use_task_env("api", monkeypatch)

    assert load_settings().bedrock_platform_principal == task_env["BEDROCK_PLATFORM_PRINCIPAL"]
