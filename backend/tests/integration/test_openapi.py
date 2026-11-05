"""The OpenAPI document the TypeScript client is generated from."""

import json

from app.openapi import render_openapi


def test_openapi_document_describes_the_health_endpoints() -> None:
    document = json.loads(render_openapi())

    operations = {
        operation["operationId"]: (path, method)
        for path, methods in document["paths"].items()
        for method, operation in methods.items()
    }
    assert operations == {
        "getHealth": ("/api/health", "get"),
        "getWorkerHealth": ("/api/health/worker", "get"),
    }


def test_openapi_document_is_rendered_deterministically() -> None:
    rendered = render_openapi()

    assert rendered == render_openapi()
    assert rendered.endswith("}\n")
