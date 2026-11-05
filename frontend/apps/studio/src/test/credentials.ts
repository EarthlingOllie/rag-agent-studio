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
    capabilities: [{ capability: "chat", models: models("anthropic.claude-sonnet-4-5-20250929-v1:0") }],
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
  capabilities: ["embeddings", "rerank"],
  check_status: "failed",
  check_failure: "quota_exceeded",
  last_checked_at: "2026-11-04T17:45:00Z",
  created_at: "2026-11-01T08:00:00Z",
};

/** Keys starting `fail-<reason>` fail their check with that reason, like the backend's fake verifier. */
function failureOf(apiKey: string): CheckFailure | undefined {
  const reasons: CheckFailure[] = ["invalid_key", "missing_model_access", "quota_exceeded", "provider_unreachable"];
  return reasons.find((reason) => apiKey.startsWith(`fail-${reason}`));
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
  return { added, rotated, checked, deleted };
}
