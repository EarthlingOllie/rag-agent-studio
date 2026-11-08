"""The OpenAPI document the TypeScript client is generated from."""

import json

from app.openapi import render_openapi

_CREDENTIAL = "/api/organisations/{organisation_id}/credentials/{credential_id}"
_PROJECT = "/api/organisations/{organisation_id}/projects/{project_id}"
_THEME_IMAGE = "/api/organisations/{organisation_id}/theme/images/{kind}"
_AGENT = f"{_PROJECT}/agents/{{agent_id}}"
_PLAYGROUND = f"{_AGENT}/playground/conversations"
_FEEDBACK = "/api/widget/agents/{public_id}/messages/{message_id}/feedback"
_RATING = "/api/widget/agents/{public_id}/conversation/rating"


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
        "startThemeImageUpload": (f"{_THEME_IMAGE}/uploads", "post"),
        "confirmThemeImageUpload": (_THEME_IMAGE, "put"),
        "removeThemeImage": (_THEME_IMAGE, "delete"),
        "getThemeImage": (_THEME_IMAGE, "get"),
        "listThemeFonts": ("/api/themes/fonts", "get"),
        "listProjects": ("/api/organisations/{organisation_id}/projects", "get"),
        "createProject": ("/api/organisations/{organisation_id}/projects", "post"),
        "getProject": ("/api/organisations/{organisation_id}/projects/{project_id}", "get"),
        "updateProject": ("/api/organisations/{organisation_id}/projects/{project_id}", "patch"),
        "archiveProject": (
            "/api/organisations/{organisation_id}/projects/{project_id}/archive",
            "post",
        ),
        "deleteProject": ("/api/organisations/{organisation_id}/projects/{project_id}", "delete"),
        "restoreProject": (
            "/api/organisations/{organisation_id}/projects/{project_id}/restore",
            "post",
        ),
        "getProjectInstructions": (f"{_PROJECT}/instructions", "get"),
        "saveProjectInstructions": (f"{_PROJECT}/instructions", "put"),
        "listProjectInstructionsVersions": (f"{_PROJECT}/instructions/versions", "get"),
        "publishProjectInstructions": (f"{_PROJECT}/instructions/versions", "post"),
        "revertProjectInstructions": (f"{_PROJECT}/instructions/revert", "post"),
        "diffProjectInstructions": (f"{_PROJECT}/instructions/diff", "get"),
        "startDocumentUpload": (f"{_PROJECT}/uploads", "post"),
        "confirmDocumentUpload": (f"{_PROJECT}/documents", "post"),
        "listDocuments": (f"{_PROJECT}/documents", "get"),
        "listDocumentStatuses": (f"{_PROJECT}/documents/statuses", "get"),
        "getDocument": (f"{_PROJECT}/documents/{{document_id}}", "get"),
        "downloadDocument": (f"{_PROJECT}/documents/{{document_id}}/download", "get"),
        "listChunks": (f"{_PROJECT}/documents/{{document_id}}/chunks", "get"),
        "getUploadLimits": (f"{_PROJECT}/uploads/limits", "get"),
        "setDocumentQuota": (f"{_PROJECT}/document-quota", "put"),
        "retryDocument": (f"{_PROJECT}/documents/{{document_id}}/retry", "post"),
        "listEmbeddingModels": ("/api/organisations/{organisation_id}/embedding-models", "get"),
        "setProjectEmbeddingModel": (f"{_PROJECT}/embedding-model", "put"),
        "getProjectEmbeddingModel": (f"{_PROJECT}/embedding-model", "get"),
        "probeRetrieval": (f"{_PROJECT}/retrieval-probe", "post"),
        "deleteDocument": (f"{_PROJECT}/documents/{{document_id}}", "delete"),
        "clearChunkFlag": (
            f"{_PROJECT}/documents/{{document_id}}/chunks/{{chunk_id}}/flag",
            "delete",
        ),
        "replaceDocument": (f"{_PROJECT}/documents/{{document_id}}/editions", "post"),
        "listTags": (f"{_PROJECT}/tags", "get"),
        "createTag": (f"{_PROJECT}/tags", "post"),
        "renameTag": (f"{_PROJECT}/tags/{{tag_id}}", "patch"),
        "deleteTag": (f"{_PROJECT}/tags/{{tag_id}}", "delete"),
        "setDocumentTags": (f"{_PROJECT}/documents/{{document_id}}/tags", "put"),
        "bulkTagDocuments": (f"{_PROJECT}/documents/tags", "post"),
        "listAgents": (f"{_PROJECT}/agents", "get"),
        "createAgent": (f"{_PROJECT}/agents", "post"),
        "getAgent": (f"{_AGENT}", "get"),
        "saveAgentDraft": (f"{_AGENT}/draft", "put"),
        "archiveAgent": (f"{_AGENT}/archive", "post"),
        "restoreAgent": (f"{_AGENT}/restore", "post"),
        "deleteAgent": (f"{_AGENT}", "delete"),
        "publishAgent": (f"{_AGENT}/versions", "post"),
        "revertAgent": (f"{_AGENT}/revert", "post"),
        "listAgentVersions": (f"{_AGENT}/versions", "get"),
        "getAgentVersion": (f"{_AGENT}/versions/{{version_id}}", "get"),
        "listAgentLiveHistory": (f"{_AGENT}/live-history", "get"),
        "getOperationalSettings": (f"{_AGENT}/operational-settings", "get"),
        "changeOperationalSettings": (f"{_AGENT}/operational-settings", "patch"),
        "getTokenUsage": (f"{_AGENT}/token-usage", "get"),
        "getThemeOverride": (f"{_AGENT}/theme-override", "get"),
        "setThemeOverrideColours": (f"{_AGENT}/theme-override", "put"),
        "startAgentAvatarUpload": (f"{_AGENT}/theme-override/avatar/uploads", "post"),
        "confirmAgentAvatarUpload": (f"{_AGENT}/theme-override/avatar", "put"),
        "removeAgentAvatar": (f"{_AGENT}/theme-override/avatar", "delete"),
        "getAgentAvatar": (f"{_AGENT}/theme-override/avatar", "get"),
        "startWidgetConversation": ("/api/widget/agents/{public_id}/conversations", "post"),
        "sendWidgetMessage": ("/api/widget/agents/{public_id}/messages", "post"),
        "getWidgetConversation": ("/api/widget/agents/{public_id}/conversation", "get"),
        "endWidgetConversation": ("/api/widget/agents/{public_id}/conversation", "delete"),
        "giveMessageFeedback": (_FEEDBACK, "put"),
        "removeMessageFeedback": (_FEEDBACK, "delete"),
        "rateConversation": (_RATING, "put"),
        "dismissRatingPrompt": (f"{_RATING}/dismissal", "post"),
        "bulkPublishAgents": (f"{_PROJECT}/agents/bulk-publish", "post"),
        "bulkRevertAgents": (f"{_PROJECT}/agents/bulk-revert", "post"),
        "getInstructionsRollout": (f"{_PROJECT}/instructions/rollout", "get"),
        "diffAgent": (f"{_AGENT}/diff", "get"),
        "discardAgentDraft": (f"{_AGENT}/draft/discard", "post"),
        "startAgentDraftFromVersion": (f"{_AGENT}/draft/from-version", "post"),
        "startPlaygroundConversation": (f"{_PLAYGROUND}", "post"),
        "getPlaygroundConversation": (f"{_PLAYGROUND}/{{conversation_id}}", "get"),
        "sendPlaygroundMessage": (f"{_PLAYGROUND}/{{conversation_id}}/messages", "post"),
        "getPlaygroundTrace": (
            f"{_PLAYGROUND}/{{conversation_id}}/messages/{{message_id}}/trace",
            "get",
        ),
        "listConversations": (f"{_PROJECT}/conversations", "get"),
        "getConversation": (f"{_PROJECT}/conversations/{{conversation_id}}", "get"),
        "getConversationTrace": (
            f"{_PROJECT}/conversations/{{conversation_id}}/messages/{{message_id}}/trace",
            "get",
        ),
        "getVersionMetrics": (f"{_PROJECT}/agents/{{agent_id}}/metrics", "get"),
        "compareVersions": (f"{_PROJECT}/agents/{{agent_id}}/comparison", "get"),
        "exportVersionComparison": (f"{_PROJECT}/agents/{{agent_id}}/comparison.csv", "get"),
        "getTimeSeries": (f"{_PROJECT}/agents/{{agent_id}}/time-series", "get"),
    }


def test_openapi_document_is_rendered_deterministically() -> None:
    rendered = render_openapi()

    assert rendered == render_openapi()
    assert rendered.endswith("}\n")


def test_the_agentconfig_json_schema_types_the_draft_editor() -> None:
    """The Studio's Draft form is typed from this schema (via the generated client)."""
    schemas = json.loads(render_openapi())["components"]["schemas"]

    saved = schemas["AgentConfig-Output"]
    assert saved["required"] == ["behaviour", "retrieval", "experience", "guardrails"]
    assert saved["additionalProperties"] is False
    behaviour = schemas["Behaviour-Output"]["properties"]
    assert behaviour["temperature"] == {
        "default": 0.7,
        "maximum": 1.0,
        "minimum": 0.0,
        "title": "Temperature",
        "type": "number",
    }
    assert behaviour["model"]["anyOf"] == [
        {"$ref": "#/components/schemas/ModelChoice"},
        {"type": "null"},
    ]
    assert schemas["Retrieval-Output"]["properties"]["reranker"]["anyOf"][0] == {
        "$ref": "#/components/schemas/ModelChoice"
    }
    assert schemas["Experience-Output"]["properties"]["starter_questions"]["maxItems"] == 6
    assert schemas["Guardrails-Output"]["properties"]["input_mode"] == {
        "$ref": "#/components/schemas/InputMode",
        "default": "block",
    }
    assert schemas["InputMode"]["enum"] == ["block", "warn", "log"]
    # The request body is the same model, with every field optional.
    assert schemas["AgentConfig-Input"].get("required") is None
