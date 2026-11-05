"""No endpoint ever returns Provider Credential secret material.

Two checks:
- the response schema of every route in the API, walked through every referenced model, has
  no field whose name says it carries a secret (the one deliberate exception, the TOTP
  enrolment secret a Member is shown once to set up their own authenticator, is listed);
- in use, the plaintext key, and its sealed form's bytes, appear in no answer of any route
  that touches a credential, including Audit Events and failures.
"""

import re
from collections.abc import Iterator
from typing import Any

import httpx

from app.main import create_app
from tests.conftest import SignedUpMember

# Field names that would mean a secret is being returned.
_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
_SECRET_WORDS = frozenset(
    {"secret", "secrets", "sealed", "ciphertext", "plaintext", "password", "passphrase"}
)
_SECRET_LAST_WORDS = frozenset({"key", "keys", "token", "tokens", "credential", "credentials"})

# (schema, field): why it may be returned.
ALLOWED = {
    # Spec 01: a Member enrolling in TOTP MFA is shown their own new secret once, to type
    # into an authenticator app. It is not a Provider Credential.
    ("EnrolmentResponse", "secret"): "a Member's own TOTP secret, shown once at enrolment",
}


def _secret_like(name: str) -> bool:
    words = [word.lower() for word in _WORD.findall(name)]
    return not _SECRET_WORDS.isdisjoint(words) or (bool(words) and words[-1] in _SECRET_LAST_WORDS)


def _fields(
    schema: dict[str, Any], schemas: dict[str, Any], seen: set[str]
) -> Iterator[tuple[str, str]]:
    """Every (model, field) reachable from ``schema``."""
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[1]
        if name in seen:
            return
        seen.add(name)
        model = schemas[name]
        for field, sub in model.get("properties", {}).items():
            yield name, field
            yield from _fields(sub, schemas, seen)
        yield from _fields({k: v for k, v in model.items() if k != "properties"}, schemas, seen)
        return
    for key in ("items", "additionalProperties"):
        if isinstance(schema.get(key), dict):
            yield from _fields(schema[key], schemas, seen)
    for key in ("anyOf", "oneOf", "allOf"):
        for sub in schema.get(key, []):
            yield from _fields(sub, schemas, seen)


def _response_fields() -> set[tuple[str, str]]:
    document = create_app().openapi()
    schemas = document["components"]["schemas"]
    found: set[tuple[str, str]] = set()
    for operations in document["paths"].values():
        for operation in operations.values():
            for response in operation.get("responses", {}).values():
                for media in response.get("content", {}).values():
                    found.update(_fields(media.get("schema", {}), schemas, set()))
    return found


def test_the_field_name_check_recognises_secret_fields() -> None:
    assert all(
        _secret_like(name)
        for name in ("api_key", "apiKey", "secret_sealed", "secret", "access_token", "password")
    )
    assert not any(
        _secret_like(name)
        for name in (
            "masked_suffix",
            "key_id",
            "check_status",
            "capabilities",
            "auth_kind",
            "role_arn",
            "external_id",
            "trust_policy",
        )
    )


def test_no_response_schema_has_a_secret_field() -> None:
    fields = _response_fields()

    # The walk reaches the credential models, so the check is not vacuous.
    assert ("CredentialOut", "masked_suffix") in fields
    assert ("CheckFailedResponse", "reason") in fields
    assert ("CredentialInUseResponse", "references") in fields
    assert ("ProviderOut", "capabilities") in fields
    assert ("BedrockSetupOut", "trust_policy") in fields
    assert {field for field in fields if _secret_like(field[1])} == set(ALLOWED)


# The random parts use letters outside hex, so they can't turn up by chance inside a UUID.
KEY = "sk-ant-api03-no-echo-qx7zrw-pk9mtn-yv2jls-q8r2"
ROTATED = "sk-ant-api03-no-echo-zmq4ny-wt8kxp-rv3hjs-t4u6"
FAILING = "fake-fail-invalid_key-no-echo-jkwz5p-mny6rq-xts8lv-v7w9"


def _leaks(response: httpx.Response, secret: str) -> bool:
    """Whether any run of 5 characters from the key's random part appears in the answer.

    The masked suffix is 4 characters, so 5 would be more of the key than is ever shown. The
    keys' readable prefixes ("sk-ant-api03", "fake-fail-invalid_key") are left out, since
    words like "invalid_key" legitimately appear as failure reasons.
    """
    exposed = response.text + str(response.headers)
    core = secret.rsplit("-no-echo-", 1)[1]
    return secret in exposed or any(core[i : i + 5] in exposed for i in range(len(core) - 4))


async def test_no_credential_route_ever_returns_the_key(owner: SignedUpMember) -> None:
    base = f"/api/organisations/{owner.organisation_id}"
    client = owner.client
    created = await client.post(
        f"{base}/credentials", json={"name": "No echo", "provider": "anthropic", "api_key": KEY}
    )
    one = f"{base}/credentials/{created.json()['id']}"
    responses = [
        created,
        await client.post(
            f"{base}/credentials",
            json={"name": "Fails", "provider": "anthropic", "api_key": FAILING},
        ),
        await client.post(
            f"{base}/credentials",
            json={"name": "Bad", "provider": "anthropic", "api_key": f"{KEY} {KEY}"},
        ),
        await client.get(f"{base}/credentials"),
        await client.get(one),
        await client.post(f"{one}/check"),
        await client.post(f"{one}/rotate", json={"api_key": ROTATED}),
        await client.post(f"{one}/rotate", json={"api_key": FAILING}),
        await client.get(f"{base}/audit-events", params={"size": 100}),
        await client.get(f"{base}/audit-events/facets"),
        await client.delete(one),
        await client.get(f"{base}/audit-events", params={"size": 100}),
    ]

    assert [r.status_code for r in responses] == [
        201, 400, 422, 200, 200, 200, 200, 400, 200, 200, 204, 200
    ]  # fmt: skip
    for response in responses:
        for secret in (KEY, ROTATED, FAILING):
            assert not _leaks(response, secret), (response.request.url, response.text)
    # The masked suffixes are all that is shown.
    assert created.json()["masked_suffix"] == "q8r2"
    assert responses[6].json()["masked_suffix"] == "t4u6"


SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG-no-echo-bPxRfiCYqzkwvn"
FAILING_SECRET = "fake-fail-wrong_region-no-echo-hqzv7wkpnmtr"


async def test_no_bedrock_route_ever_returns_the_secret_access_key(owner: SignedUpMember) -> None:
    base = f"/api/organisations/{owner.organisation_id}"
    client = owner.client
    keys = {
        "auth_kind": "aws_access_keys",
        "access_key_id": "AKIAIOSFODNN7EXAMPLE",
        "region": "us-east-1",
    }
    created = await client.post(
        f"{base}/credentials/bedrock",
        json={"name": "Keys", "secret_access_key": SECRET_ACCESS_KEY, **keys},
    )
    one = f"{base}/credentials/{created.json()['id']}"
    responses = [
        created,
        await client.post(
            f"{base}/credentials/bedrock",
            json={"name": "Fails", "secret_access_key": FAILING_SECRET, **keys},
        ),
        await client.post(
            f"{base}/credentials/bedrock",
            json={"name": "Bad", "secret_access_key": f"{SECRET_ACCESS_KEY} x", **keys},
        ),
        await client.get(f"{base}/credentials"),
        await client.get(one),
        await client.post(f"{one}/check"),
        await client.get(f"{base}/bedrock-setup"),
        await client.get(f"{base}/audit-events", params={"size": 100}),
        await client.delete(one),
        await client.get(f"{base}/audit-events", params={"size": 100}),
    ]

    assert [r.status_code for r in responses] == [
        201, 400, 422, 200, 200, 200, 200, 200, 204, 200
    ]  # fmt: skip
    for response in responses:
        for secret in (SECRET_ACCESS_KEY, FAILING_SECRET):
            assert not _leaks(response, secret), (response.request.url, response.text)
    assert created.json()["masked_suffix"] == "MPLE"
