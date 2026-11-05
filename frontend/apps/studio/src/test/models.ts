import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import { type Credential, marketingOpenAi } from "./credentials";
import { server } from "./server";

export type DefaultModel = Schemas["DefaultModelOut"];
type ModelOut = Schemas["ModelOut"];

/** Chat models per credential ID, as `GET …/credentials/{id}/models/chat` answers them. */
export const chatModels: Record<string, ModelOut[]> = {
  [marketingOpenAi.id]: [
    { id: "gpt-4.1", name: "GPT-4.1" },
    { id: "gpt-4.1-mini", name: "GPT-4.1 mini" },
  ],
};

export const legalClaude: Credential = {
  ...marketingOpenAi,
  id: "c0000000-0000-4000-8000-000000000003",
  name: "Legal Claude",
  provider: "anthropic",
  masked_suffix: "abcd",
  capabilities: ["chat"],
};
chatModels[legalClaude.id] = [
  { id: "claude-sonnet-4-5", name: "Claude Sonnet 4.5" },
  { id: "claude-haiku-4-5", name: "Claude Haiku 4.5" },
];

export const embeddingsOnlyOpenAi: Credential = {
  ...marketingOpenAi,
  id: "c0000000-0000-4000-8000-000000000004",
  name: "Search OpenAI",
  capabilities: ["embeddings"],
};

export const claudeDefault: DefaultModel = {
  credential_id: legalClaude.id,
  credential_name: "Legal Claude",
  provider: "anthropic",
  model: "claude-haiku-4-5",
  model_name: "Claude Haiku 4.5",
  updated_at: "2026-11-05T09:00:00Z",
};

/**
 * A stateful stand-in for the Default Model API. Setting a model the credential doesn't offer
 * for chat is refused with 422, as the API does. Records what it receives.
 */
export function fakeModelsApi(options: { defaultModel?: DefaultModel | null; credentials?: Credential[] } = {}) {
  let current = options.defaultModel ?? null;
  const credentials = options.credentials ?? [marketingOpenAi, legalClaude, embeddingsOnlyOpenAi];
  const set: Schemas["SetDefaultModelRequest"][] = [];
  const listed: string[] = [];
  server.use(
    http.get("*/api/organisations/:organisationId/credentials", () => HttpResponse.json(credentials)),
    http.get("*/api/organisations/:organisationId/credentials/:credentialId/models/:capability", ({ params }) => {
      const id = params.credentialId as string;
      listed.push(`${id}/${params.capability as string}`);
      return HttpResponse.json(chatModels[id] ?? []);
    }),
    http.get("*/api/organisations/:organisationId/default-model", () => HttpResponse.json(current)),
    http.put("*/api/organisations/:organisationId/default-model", async ({ request }) => {
      const body = (await request.json()) as Schemas["SetDefaultModelRequest"];
      set.push(body);
      const credential = credentials.find((c) => c.id === body.credential_id) as Credential;
      const model = (chatModels[credential.id] ?? []).find((m) => m.id === body.model);
      if (!model) return HttpResponse.json({ detail: `That model isn't offered for chat.` }, { status: 422 });
      current = {
        credential_id: credential.id,
        credential_name: credential.name,
        provider: credential.provider,
        model: model.id,
        model_name: model.name,
        updated_at: "2026-11-05T10:00:00Z",
      };
      return HttpResponse.json(current);
    }),
  );
  return { set, listed };
}
