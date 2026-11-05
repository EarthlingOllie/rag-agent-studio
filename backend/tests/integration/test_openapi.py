"""The OpenAPI document the TypeScript client is generated from."""

import json

from app.openapi import render_openapi


def test_openapi_document_describes_every_endpoint() -> None:
    document = json.loads(render_openapi())

    operations = {
        operation["operationId"]: (path, method)
        for path, methods in document["paths"].items()
        for method, operation in methods.items()
    }
    assert operations == {
        "getHealth": ("/api/health", "get"),
        "getWorkerHealth": ("/api/health/worker", "get"),
        "signUp": ("/api/auth/sign-up", "post"),
        "signIn": ("/api/auth/sign-in", "post"),
        "signOut": ("/api/auth/sign-out", "post"),
        "getMe": ("/api/auth/me", "get"),
        "getMfaStatus": ("/api/auth/mfa", "get"),
        "startMfaEnrolment": ("/api/auth/mfa/enrolment", "post"),
        "confirmMfaEnrolment": ("/api/auth/mfa/enrolment/confirm", "post"),
        "verifyMfa": ("/api/auth/mfa/verify", "post"),
        "replaceRecoveryCodes": ("/api/auth/mfa/recovery-codes", "post"),
        "disableMfa": ("/api/auth/mfa/disable", "post"),
        "updateProfile": ("/api/auth/me", "patch"),
        "changePassword": ("/api/auth/me/password", "post"),
        "requestPasswordReset": ("/api/auth/password-reset", "post"),
        "completePasswordReset": ("/api/auth/password-reset/complete", "post"),
        "getOrganisation": ("/api/organisations/{organisation_id}", "get"),
        "listAuditEvents": ("/api/organisations/{organisation_id}/audit-events", "get"),
        "getAuditFacets": ("/api/organisations/{organisation_id}/audit-events/facets", "get"),
    }


def test_openapi_document_is_rendered_deterministically() -> None:
    rendered = render_openapi()

    assert rendered == render_openapi()
    assert rendered.endswith("}\n")
