import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import { type Credential, marketingOpenAi } from "./credentials";
import { server } from "./server";

export type DefaultModel = Schemas["DefaultModelOut"];
type ModelOut = Schemas["ModelOut"];

/** Chat models per credential ID, as `GET …/credentials/{id}/models/chat` answers them. */
export const chatModels: Record<string, ModelOut[]> = {
  [marketingOpenAi.id]: [
    { id: "gpt-4.1", name: "GPT-4.1", supports_tools: true },
    { id: "gpt-4.1-mini", name: "GPT-4.1 mini", supports_tools: true },
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
  { id: "claude-sonnet-4-5", name: "Claude Sonnet 4.5", supports_tools: true },
  { id: "claude-haiku-4-5", name: "Claude Haiku 4.5", supports_tools: true },
];

export const embeddingsOnlyOpenAi: Credential = {
  ...marketingOpenAi,
  id: "c0000000-0000-4000-8000-000000000004",
  name: "Search OpenAI",
  capabilities: ["embeddings"],
};

/** The seed's demo credential: the demo provider's one model, which needs no API key. */
export const demoCredential: Credential = {
  ...marketingOpenAi,
  id: "c0000000-0000-4000-8000-000000000005",
  name: "Northwind demo model",
  provider: "demo",
  masked_suffix: "eded",
  capabilities: ["chat"],
};
chatModels[demoCredential.id] = [{ id: "demo-chat", name: "Demo model", supports_tools: true }];

export const demoDefault: DefaultModel = {
  credential_id: demoCredential.id,
  credential_name: demoCredential.name,
  provider: "demo",
  model: "demo-chat",
  model_name: "Demo model",
  supports_tools: true,
  updated_at: "2026-11-06T09:00:00Z",
};

export const claudeDefault: DefaultModel = {
  credential_id: legalClaude.id,
  credential_name: "Legal Claude",
  provider: "anthropic",
  model: "claude-haiku-4-5",
  model_name: "Claude Haiku 4.5",
  supports_tools: true,
  updated_at: "2026-11-05T09:00:00Z",
};

/**
 * A stateful stand-in for the Default Model API. Setting a model the credential doesn't offer
 * for chat is refused with 422, as the API does. Records what it receives.
 */
export function fakeModelsApi(
  options: {
    defaultModel?: DefaultModel | null;
    credentials?: Credential[];
    evaluationModel?: EvaluationSettings["evaluation_model"];
    repeats?: number;
  } = {},
) {
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
        supports_tools: model.supports_tools,
        updated_at: "2026-11-05T10:00:00Z",
      };
      return HttpResponse.json(current);
    }),
  );
  fakePricesApi();
  const evaluation = fakeEvaluationSettingsApi({ credentials, evaluationModel: options.evaluationModel, repeats: options.repeats });
  return { set, listed, evaluation };
}

export type EvaluationSettings = Schemas["EvaluationSettingsOut"];

export const claudeJudge: NonNullable<EvaluationSettings["evaluation_model"]> = {
  credential_id: legalClaude.id,
  credential_name: "Legal Claude",
  provider: "anthropic",
  model: "claude-sonnet-4-5",
  model_name: "Claude Sonnet 4.5",
};

/**
 * A stateful stand-in for the evaluation settings routes: the Evaluation Model (null while the
 * Default Model judges) and the Evaluation repeats. Records what it receives.
 */
export function fakeEvaluationSettingsApi(
  options: { credentials?: Credential[]; evaluationModel?: EvaluationSettings["evaluation_model"] | undefined; repeats?: number | undefined } = {},
) {
  const credentials = options.credentials ?? [marketingOpenAi, legalClaude];
  let current: EvaluationSettings = { evaluation_model: options.evaluationModel ?? null, repeats: options.repeats ?? 3 };
  const models: Schemas["SetEvaluationModelRequest"][] = [];
  const repeats: number[] = [];
  server.use(
    http.get("*/api/organisations/:organisationId/evaluation-settings", () => HttpResponse.json(current)),
    http.put("*/api/organisations/:organisationId/evaluation-model", async ({ request }) => {
      const body = (await request.json()) as Schemas["SetEvaluationModelRequest"];
      models.push(body);
      const credential = credentials.find((c) => c.id === body.credential_id);
      const model = credential && (chatModels[credential.id] ?? []).find((m) => m.id === body.model);
      current = {
        ...current,
        evaluation_model:
          credential && model
            ? { credential_id: credential.id, credential_name: credential.name, provider: credential.provider, model: model.id, model_name: model.name }
            : null,
      };
      return HttpResponse.json(current);
    }),
    http.put("*/api/organisations/:organisationId/evaluation-repeats", async ({ request }) => {
      const body = (await request.json()) as Schemas["SetEvaluationRepeatsRequest"];
      repeats.push(body.repeats);
      current = { ...current, repeats: body.repeats };
      return HttpResponse.json(current);
    }),
  );
  return { models, repeats };
}

export type EvaluationBudget = Schemas["EvaluationBudgetOut"];

/**
 * A stateful stand-in for the Evaluation budget routes: the budget (null: none) and November 2026's spend against
 * it, exhausted once the spend reaches the budget. Records each budget set.
 */
export function fakeEvaluationBudgetApi(options: { budget?: string | null; spent?: string } = {}) {
  const spent = options.spent ?? "0";
  const of = (budget: string | null): EvaluationBudget => ({
    evaluation_budget_usd: budget,
    month: "2026-11-01",
    spent_usd: spent,
    exhausted: budget !== null && Number(spent) >= Number(budget),
    resets_at: "2026-12-01T00:00:00Z",
  });
  let current = of(options.budget ?? null);
  const set: (string | number | null)[] = [];
  server.use(
    http.get("*/api/organisations/:organisationId/evaluation-budget", () => HttpResponse.json(current)),
    http.put("*/api/organisations/:organisationId/evaluation-budget", async ({ request }) => {
      const body = (await request.json()) as Schemas["SetEvaluationBudgetRequest"];
      set.push(body.evaluation_budget_usd);
      current = of(body.evaluation_budget_usd === null ? null : Number(body.evaluation_budget_usd).toFixed(2));
      return HttpResponse.json(current);
    }),
  );
  return { set };
}

export type JudgingGuidance = Schemas["JudgingGuidanceOut"];
type GuidanceVersion = Schemas["GuidanceVersionOut"];

export const PARTIAL_GUIDANCE = "Partial answers that say what they don't cover pass.";

export function guidanceVersion(
  version: number,
  text: string,
  savedBy: string | null = "Ada Lovelace",
  check: GuidanceVersion["check"] = null,
): GuidanceVersion {
  return { version, text, source: "written", saved_by: savedBy, saved_at: `2026-11-${String(10 + version)}T09:30:00Z`, check };
}

export type GuidanceJob = Schemas["GuidanceJobOut"];

/** A finished check of `text` on 12 held-out reviews: it would agree on 10, against 7 now. */
export function guidanceCheck(text: string, overrides: Partial<GuidanceJob> = {}): GuidanceJob {
  return {
    id: "job-1",
    kind: "check",
    status: "completed",
    text,
    held_out: 12,
    judged: 12,
    left_out: 0,
    agreed: 10,
    false_passes: 1,
    false_fails: 1,
    agreed_before: 7,
    low_sample: true,
    cost_usd: "0.0034",
    error_reason: null,
    requested_by: "Ada Lovelace",
    created_at: "2026-11-24T09:00:00Z",
    started_at: "2026-11-24T09:00:01Z",
    finished_at: "2026-11-24T09:00:30Z",
    ...overrides,
  };
}

/**
 * Guidance jobs as `GET …/guidance-jobs/latest` answers them (`latest`, null before the first).
 * Starting a check answers it running on 12 held-out reviews; each later read answers the next of
 * `then` (the last one stays). Cancelling answers the job cancelled.
 */
export function fakeGuidanceJobApi(options: { latest?: GuidanceJob | null; then?: Partial<GuidanceJob>[] } = {}) {
  let latest = options.latest ?? null;
  const steps = [...(options.then ?? [])];
  const started: string[] = [];
  const cancelled: string[] = [];
  server.use(
    http.get("*/api/organisations/:organisationId/guidance-jobs/latest", () => {
      if (latest !== null && steps.length > 0) latest = { ...latest, ...(steps.length > 1 ? steps.shift() : steps[0]) };
      return HttpResponse.json(latest);
    }),
    http.post("*/api/organisations/:organisationId/judging-guidance/checks", async ({ request }) => {
      const text = ((await request.json()) as Schemas["StartCheckRequest"]).text.trim();
      started.push(text);
      latest = guidanceCheck(text, { id: `job-${String(started.length + 1)}`, status: "running", judged: 0, agreed: 0, false_passes: 0, false_fails: 0, agreed_before: 0, finished_at: null });
      return HttpResponse.json(latest, { status: 202 });
    }),
    http.post("*/api/organisations/:organisationId/guidance-jobs/:jobId/cancel", ({ params }) => {
      cancelled.push(String(params.jobId));
      steps.length = 0;
      latest = { ...(latest as GuidanceJob), status: "cancelled" };
      return HttpResponse.json(latest);
    }),
  );
  return { started, cancelled };
}

/** Judging guidance as `GET …/judging-guidance` answers it; an Owner's save adds a version unless the text is already current. */
export function fakeJudgingGuidanceApi(options: { versions?: GuidanceVersion[] } = {}) {
  let versions = options.versions ?? [];
  const saved: string[] = [];
  const current = (): JudgingGuidance => ({ current: versions[0] ?? null, versions });
  server.use(
    http.get("*/api/organisations/:organisationId/judging-guidance", () => HttpResponse.json(current())),
    http.put("*/api/organisations/:organisationId/judging-guidance", async ({ request }) => {
      const text = ((await request.json()) as Schemas["SaveJudgingGuidanceRequest"]).text.trim();
      saved.push(text);
      if ((versions[0]?.text ?? "") !== text) versions = [guidanceVersion(versions.length + 1, text), ...versions];
      return HttpResponse.json(current());
    }),
  );
  return { saved };
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
