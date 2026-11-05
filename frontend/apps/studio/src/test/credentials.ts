import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import { server } from "./server";

export type Credential = Schemas["CredentialOut"];
type Provider = Schemas["ProviderOut"];
type Reference = Schemas["CredentialReferenceOut"];
type CheckFailure = Schemas["CheckFailedResponse"]["reason"];

const models = (...ids: string[]) => ids.map((id) => ({ id, name: id }));

/** The capability registry as `GET /api/providers` answers it. */
export const providers: Provider[] = [
  { id: "anthropic", name: "Anthropic", auth_kinds: ["api_key"], capabilities: [{ capability: "chat", models: models("claude-sonnet-4-5") }] },
  {
    id: "openai",
    name: "OpenAI",
    auth_kinds: ["api_key"],
    capabilities: [
      { capability: "chat", models: models("gpt-4.1") },
      { capability: "embeddings", models: models("text-embedding-3-small") },
    ],
  },
  {
    id: "bedrock",
    name: "Amazon Bedrock",
    auth_kinds: ["aws_role", "aws_access_keys"],
    capabilities: [
      { capability: "chat", models: models("anthropic.claude-sonnet-4-5-20250929-v1:0") },
      { capability: "embeddings", models: models("amazon.titan-embed-text-v2:0") },
      { capability: "rerank", models: models("cohere.rerank-v3-5:0") },
    ],
  },
  {
    id: "voyage",
    name: "Voyage AI",
    auth_kinds: ["api_key"],
    capabilities: [
      { capability: "embeddings", models: models("voyage-3.5") },
      { capability: "rerank", models: models("rerank-2.5") },
    ],
  },
];

export const marketingOpenAi: Credential = {
  id: "c0000000-0000-4000-8000-000000000001",
  name: "Marketing OpenAI",
  provider: "openai",
  auth_kind: "api_key",
  masked_suffix: "wxyz",
  role_arn: null,
  region: null,
  capabilities: ["chat", "embeddings"],
  check_status: "passed",
  check_failure: null,
  last_checked_at: "2026-11-05T09:00:00Z",
  created_at: "2026-11-05T09:00:00Z",
};

export const legalVoyage: Credential = {
  id: "c0000000-0000-4000-8000-000000000002",
  name: "Legal Voyage",
  provider: "voyage",
  auth_kind: "api_key",
  masked_suffix: "9876",
  role_arn: null,
  region: null,
  capabilities: ["embeddings", "rerank"],
  check_status: "failed",
  check_failure: "quota_exceeded",
  last_checked_at: "2026-11-04T17:45:00Z",
  created_at: "2026-11-01T08:00:00Z",
};

export const bedrockRole: Credential = {
  id: "c0000000-0000-4000-8000-000000000003",
  name: "Bedrock prod",
  provider: "bedrock",
  auth_kind: "aws_role",
  masked_suffix: null,
  role_arn: "arn:aws:iam::111122223333:role/StudioBedrockAccess",
  region: "eu-west-2",
  capabilities: ["chat", "embeddings", "rerank"],
  check_status: "failed",
  check_failure: "role_not_assumable",
  last_checked_at: "2026-11-05T10:00:00Z",
  created_at: "2026-11-05T08:00:00Z",
};

export const bedrockKeys: Credential = {
  ...bedrockRole,
  id: "c0000000-0000-4000-8000-000000000004",
  name: "Bedrock sandbox",
  auth_kind: "aws_access_keys",
  masked_suffix: "MPLE",
  role_arn: null,
  region: "us-east-1",
  check_status: "passed",
  check_failure: null,
};

export const bedrockSetup: Schemas["BedrockSetupOut"] = {
  external_id: "k2Jd8wQm4Zr7Vt1Xy9Pb3Lc6Ns0Hf5Ga",
  platform_principal: "arn:aws:iam::000000000000:role/rag-agent-studio-local",
  trust_policy: '{\n  "Version": "2012-10-17",\n  "Statement": ["trust k2Jd8wQm4Zr7Vt1Xy9Pb3Lc6Ns0Hf5Ga"]\n}',
  permissions_policy: '{\n  "Version": "2012-10-17",\n  "Statement": ["bedrock:InvokeModel"]\n}',
};

/** Values starting `fail-<reason>` fail their check with that reason, like the backend's fake verifier. */
function failureOf(value: string): CheckFailure | undefined {
  const reasons: CheckFailure[] = [
    "invalid_key",
    "missing_model_access",
    "quota_exceeded",
    "provider_unreachable",
    "role_not_assumable",
    "wrong_region",
  ];
  return reasons.find((reason) => value.startsWith(`fail-${reason}`));
}

const checkFailed = (reason: CheckFailure) => HttpResponse.json({ detail: `API says ${reason}`, reason }, { status: 400 });

/**
 * A stateful stand-in for the credentials API. Records what it receives. `references` maps a
 * credential ID to what still uses it; `recheck` sets the outcome of the next re-check.
 */
export function fakeCredentialsApi(
  options: { credentials?: Credential[]; references?: Record<string, Reference[]>; recheck?: CheckFailure | null } = {},
) {
  let credentials = [...(options.credentials ?? [marketingOpenAi, legalVoyage])];
  const added: unknown[] = [];
  let setupRequests = 0;
  const rotated: { id: string; apiKey: string }[] = [];
  const checked: string[] = [];
  const deleted: string[] = [];
  const references = options.references ?? {};
  const sorted = () => [...credentials].sort((a, b) => a.name.localeCompare(b.name));
  const replace = (next: Credential) => {
    credentials = credentials.map((c) => (c.id === next.id ? next : c));
    return HttpResponse.json(next);
  };
  const find = (id: unknown) => credentials.find((c) => c.id === id) as Credential;
  server.use(
    http.get("*/api/providers", () => HttpResponse.json(providers)),
    http.get("*/api/organisations/:organisationId/credentials", () => HttpResponse.json(sorted())),
    http.post("*/api/organisations/:organisationId/credentials", async ({ request }) => {
      const body = (await request.json()) as Schemas["CreateCredentialRequest"];
      added.push(body);
      const reason = failureOf(body.api_key);
      if (reason) return checkFailed(reason);
      if (credentials.some((c) => c.name === body.name)) {
        return HttpResponse.json({ detail: "Another credential in this Organisation already has that name." }, { status: 409 });
      }
      const credential: Credential = {
        ...marketingOpenAi,
        id: `c0000000-0000-4000-8000-${String(credentials.length + 100).padStart(12, "0")}`,
        name: body.name,
        provider: body.provider,
        masked_suffix: body.api_key.slice(-4),
        capabilities: body.capabilities ?? [],
      };
      credentials.push(credential);
      return HttpResponse.json(credential, { status: 201 });
    }),
    http.get("*/api/organisations/:organisationId/bedrock-setup", () => {
      setupRequests += 1;
      return HttpResponse.json(bedrockSetup);
    }),
    http.post("*/api/organisations/:organisationId/credentials/bedrock", async ({ request }) => {
      const body = (await request.json()) as Schemas["CreateBedrockRoleRequest"] | Schemas["CreateBedrockAccessKeysRequest"];
      added.push(body);
      const reason = failureOf(body.auth_kind === "aws_role" ? (body.role_arn.split("/").pop() ?? "") : body.secret_access_key);
      if (reason) return checkFailed(reason);
      const credential: Credential = {
        ...(body.auth_kind === "aws_role" ? bedrockRole : bedrockKeys),
        id: `c0000000-0000-4000-8000-${String(credentials.length + 100).padStart(12, "0")}`,
        name: body.name,
        role_arn: body.auth_kind === "aws_role" ? body.role_arn : null,
        masked_suffix: body.auth_kind === "aws_role" ? null : body.access_key_id.slice(-4),
        region: body.region,
        capabilities: body.capabilities ?? [],
        check_status: "passed",
        check_failure: null,
      };
      credentials.push(credential);
      return HttpResponse.json(credential, { status: 201 });
    }),
    http.post("*/api/organisations/:organisationId/credentials/:credentialId/check", ({ params }) => {
      checked.push(params.credentialId as string);
      const failure = options.recheck ?? null;
      return replace({
        ...find(params.credentialId),
        check_status: failure ? "failed" : "passed",
        check_failure: failure,
        last_checked_at: "2026-11-05T12:00:00Z",
      });
    }),
    http.post("*/api/organisations/:organisationId/credentials/:credentialId/rotate", async ({ params, request }) => {
      const { api_key: apiKey } = (await request.json()) as Schemas["RotateCredentialRequest"];
      rotated.push({ id: params.credentialId as string, apiKey });
      const reason = failureOf(apiKey);
      if (reason) return checkFailed(reason);
      return replace({ ...find(params.credentialId), masked_suffix: apiKey.slice(-4), check_status: "passed", check_failure: null });
    }),
    http.delete("*/api/organisations/:organisationId/credentials/:credentialId", ({ params }) => {
      const id = params.credentialId as string;
      deleted.push(id);
      const users = references[id] ?? [];
      if (users.length > 0) {
        return HttpResponse.json({ detail: "This credential is still in use.", references: users }, { status: 409 });
      }
      credentials = credentials.filter((c) => c.id !== id);
      return new HttpResponse(null, { status: 204 });
    }),
  );
  return {
    added,
    rotated,
    checked,
    deleted,
    get setupRequests() {
      return setupRequests;
    },
  };
}
