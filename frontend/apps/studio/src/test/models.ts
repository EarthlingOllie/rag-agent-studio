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
  fakePricesApi();
  return { set, listed };
}

type ModelPrices = Schemas["ModelPricesOut"];
type PriceOverride = Schemas["OverridePricesRequest"];

/** Prices per credential ID, as `GET …/credentials/{id}/prices` answers them before overrides. */
export const platformPrices: Record<string, ModelPrices[]> = {
  [legalClaude.id]: [
    {
      model: "claude-sonnet-4-5",
      model_name: "Claude Sonnet 4.5",
      capability: "chat",
      platform: { input: "3", output: "15", cached_input: "0.3" },
      override: null,
      effective: { input: "3", output: "15", cached_input: "0.3" },
    },
    {
      model: "claude-haiku-4-5",
      model_name: "Claude Haiku 4.5",
      capability: "chat",
      platform: { input: "1", output: "5", cached_input: "0.1" },
      override: null,
      effective: { input: "1", output: "5", cached_input: "0.1" },
    },
  ],
  [marketingOpenAi.id]: [
    {
      model: "gpt-4.1",
      model_name: "GPT-4.1",
      capability: "chat",
      platform: { input: "2", output: "8", cached_input: "0.5" },
      override: null,
      effective: { input: "2", output: "8", cached_input: "0.5" },
    },
    {
      model: "text-embedding-3-small",
      model_name: "text-embedding-3-small",
      capability: "embeddings",
      platform: null,
      override: null,
      effective: { input: null, output: null, cached_input: null },
    },
  ],
};

/**
 * A stateful stand-in for the price routes: overrides apply as the API applies them (each
 * price overrides the platform's; none clears the override). Records what it receives.
 */
export function fakePricesApi(options: { prices?: Record<string, ModelPrices[]> } = {}) {
  const prices = structuredClone(options.prices ?? platformPrices);
  const overridden: { credentialId: string; body: PriceOverride }[] = [];
  server.use(
    http.get("*/api/organisations/:organisationId/credentials/:credentialId/prices", ({ params }) => {
      const id = params.credentialId as string;
      return HttpResponse.json({ credential_id: id, currency: "USD", unit: "per million tokens", models: prices[id] ?? [] });
    }),
    http.put("*/api/organisations/:organisationId/credentials/:credentialId/prices", async ({ params, request }) => {
      const id = params.credentialId as string;
      const body = (await request.json()) as PriceOverride;
      overridden.push({ credentialId: id, body });
      const rows = prices[id] ?? [];
      const index = rows.findIndex((row) => row.model === body.model);
      const row = rows[index] as ModelPrices;
      const pick = (kind: "input" | "output" | "cached_input") => {
        const value = body[kind];
        return value === undefined || value === null ? null : String(value);
      };
      const override = { input: pick("input"), output: pick("output"), cached_input: pick("cached_input") };
      const cleared = override.input === null && override.output === null && override.cached_input === null;
      const next: ModelPrices = {
        ...row,
        override: cleared ? null : override,
        effective: {
          input: override.input ?? row.platform?.input ?? null,
          output: override.output ?? row.platform?.output ?? null,
          cached_input: override.cached_input ?? row.platform?.cached_input ?? null,
        },
      };
      rows[index] = next;
      return HttpResponse.json(next);
    }),
  );
  return { overridden };
}
