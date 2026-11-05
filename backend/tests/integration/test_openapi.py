"""The OpenAPI document the TypeScript client is generated from."""

import json

from app.openapi import render_openapi

_CREDENTIAL = "/api/organisations/{organisation_id}/credentials/{credential_id}"
_PROJECT = "/api/organisations/{organisation_id}/projects/{project_id}"


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
        "switchOrganisation": ("/api/auth/me/active-organisation", "put"),
        "requestPasswordReset": ("/api/auth/password-reset", "post"),
        "completePasswordReset": ("/api/auth/password-reset/complete", "post"),
        "getOrganisation": ("/api/organisations/{organisation_id}", "get"),
        "setMfaPolicy": ("/api/organisations/{organisation_id}/mfa-policy", "put"),
        "listAuditEvents": ("/api/organisations/{organisation_id}/audit-events", "get"),
        "getAuditFacets": ("/api/organisations/{organisation_id}/audit-events/facets", "get"),
        "listInvites": ("/api/organisations/{organisation_id}/invites", "get"),
        "createInvite": ("/api/organisations/{organisation_id}/invites", "post"),
        "revokeInvite": ("/api/organisations/{organisation_id}/invites/{invite_id}", "delete"),
        "renewInvite": ("/api/organisations/{organisation_id}/invites/{invite_id}/renew", "post"),
        "lookUpInvite": ("/api/invites/lookup", "post"),
        "acceptInvite": ("/api/invites/accept", "post"),
        "signUpWithInvite": ("/api/invites/sign-up", "post"),
        "listMembers": ("/api/organisations/{organisation_id}/members", "get"),
        "changeMemberRole": ("/api/organisations/{organisation_id}/members/{member_id}", "patch"),
        "removeMember": ("/api/organisations/{organisation_id}/members/{member_id}", "delete"),
        "leaveOrganisation": ("/api/organisations/{organisation_id}/leave", "post"),
        "listCredentials": ("/api/organisations/{organisation_id}/credentials", "get"),
        "createCredential": ("/api/organisations/{organisation_id}/credentials", "post"),
        "getCredential": (_CREDENTIAL, "get"),
        "deleteCredential": (_CREDENTIAL, "delete"),
        "checkCredential": (f"{_CREDENTIAL}/check", "post"),
        "rotateCredential": (f"{_CREDENTIAL}/rotate", "post"),
        "createBedrockCredential": (
            "/api/organisations/{organisation_id}/credentials/bedrock",
            "post",
        ),
        "getBedrockSetup": ("/api/organisations/{organisation_id}/bedrock-setup", "get"),
        "listCredentialModels": (f"{_CREDENTIAL}/models/{{capability}}", "get"),
        "listCredentialPrices": (f"{_CREDENTIAL}/prices", "get"),
        "overrideCredentialPrices": (f"{_CREDENTIAL}/prices", "put"),
        "listProviders": ("/api/providers", "get"),
        "getDefaultModel": ("/api/organisations/{organisation_id}/default-model", "get"),
        "setDefaultModel": ("/api/organisations/{organisation_id}/default-model", "put"),
        "getTheme": ("/api/organisations/{organisation_id}/theme", "get"),
        "saveTheme": ("/api/organisations/{organisation_id}/theme", "put"),
        "listThemeFonts": ("/api/themes/fonts", "get"),
        "listProjects": ("/api/organisations/{organisation_id}/projects", "get"),
        "createProject": ("/api/organisations/{organisation_id}/projects", "post"),
        "getProject": ("/api/organisations/{organisation_id}/projects/{project_id}", "get"),
        "updateProject": ("/api/organisations/{organisation_id}/projects/{project_id}", "patch"),
        "archiveProject": (
            "/api/organisations/{organisation_id}/projects/{project_id}/archive",
            "post",
        ),
        "restoreProject": (
            "/api/organisations/{organisation_id}/projects/{project_id}/restore",
            "post",
        ),
        "startDocumentUpload": (f"{_PROJECT}/uploads", "post"),
        "confirmDocumentUpload": (f"{_PROJECT}/documents", "post"),
        "listDocuments": (f"{_PROJECT}/documents", "get"),
        "listDocumentStatuses": (f"{_PROJECT}/documents/statuses", "get"),
        "listChunks": (f"{_PROJECT}/documents/{{document_id}}/chunks", "get"),
        "listEmbeddingModels": ("/api/organisations/{organisation_id}/embedding-models", "get"),
        "setProjectEmbeddingModel": (f"{_PROJECT}/embedding-model", "put"),
        "probeRetrieval": (f"{_PROJECT}/retrieval-probe", "post"),
    }


def test_openapi_document_is_rendered_deterministically() -> None:
    rendered = render_openapi()

    assert rendered == render_openapi()
    assert rendered.endswith("}\n")
