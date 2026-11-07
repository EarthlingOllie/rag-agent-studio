import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import { server } from "./server";

type RolloutAgent = Schemas["RolloutAgentOut"];
type Rollout = Schemas["InstructionsRolloutOut"];
type Outcome = Schemas["BulkOutcomeOut"];

export const BULK_OPERATION_ID = "b0000000-0000-4000-8000-000000000001";
export const NEVER_PUBLISHED = "Never published, so it has no Live configuration to build from. Publish it from its page first.";
export const NOTHING_TO_REVERT = "There's no earlier Live Version to revert to.";

const versionId = (agent: number, number: number) => `a2e00000-0000-4000-8000-${String(agent * 100 + number).padStart(12, "0")}`;

/** A row of the Instructions rollout: the `index`th Agent, Live at `live` pinning `instructions`. */
export function rolloutAgent(
  index: number,
  name: string,
  live: number | null,
  instructions: { id: string; number: number } | null,
  overrides: Partial<RolloutAgent> = {},
): RolloutAgent {
  return {
    id: `a9e00000-0000-4000-8000-${String(index).padStart(12, "0")}`,
    name,
    live_version: live === null ? null : { id: versionId(index, live), number: live },
    instructions_version: instructions,
    has_draft_changes: false,
    behind: false,
    ...overrides,
  };
}

/**
 * Fakes the bulk routes and the rollout summary, in memory. A bulk publish makes each named
 * Agent's next Version Live with the chosen Instructions (skipping never-published Agents), a
 * bulk revert steps each back one Version (skipping those on v1 or not live). Records the
 * requests it receives.
 */
export function fakeBulkApi(
  options: {
    rollout?: Rollout;
    /** Answers each bulk action instead of the fake's own rules. */
    respond?: () => Response;
  } = {},
) {
  const rollout: Rollout = options.rollout ?? { current_version: null, behind: 0, agents: [] };
  const requests: { route: string; body: unknown }[] = [];
  const find = (id: string) => rollout.agents.find((agent) => agent.id === id);
  const outcome = (id: string, change: (agent: RolloutAgent) => Partial<Outcome>): Outcome => {
    const agent = find(id);
    const base: Outcome = { agent_id: id, name: agent?.name ?? null, status: "failed", reason: "Not found.", live_version: null, instructions_version: null };
    return agent ? { ...base, ...change(agent) } : base;
  };
  const answer = (results: Outcome[]) => options.respond?.() ?? HttpResponse.json({ bulk_operation_id: BULK_OPERATION_ID, results });
  server.use(
    http.get("*/api/organisations/:organisationId/projects/:projectId/instructions/rollout", () => HttpResponse.json(rollout)),
    http.post("*/api/organisations/:organisationId/projects/:projectId/agents/bulk-publish", async ({ request }) => {
      const body = (await request.json()) as Schemas["BulkPublishRequest"];
      requests.push({ route: "bulk-publish", body });
      const pinned = rollout.current_version?.id === body.instructions_version_id ? rollout.current_version : null;
      return answer(
        body.agent_ids.map((id, index) =>
          outcome(id, (agent) =>
            agent.live_version
              ? {
                  status: "succeeded",
                  reason: null,
                  live_version: { id: versionId(index, agent.live_version.number + 1), number: agent.live_version.number + 1 },
                  instructions_version: pinned,
                }
              : { status: "skipped", reason: NEVER_PUBLISHED },
          ),
        ),
      );
    }),
    http.post("*/api/organisations/:organisationId/projects/:projectId/agents/bulk-revert", async ({ request }) => {
      const body = (await request.json()) as Schemas["BulkRevertRequest"];
      requests.push({ route: "bulk-revert", body });
      return answer(
        body.agent_ids.map((id, index) =>
          outcome(id, (agent) =>
            agent.live_version && agent.live_version.number > 1
              ? {
                  status: "succeeded",
                  reason: null,
                  live_version: { id: versionId(index, agent.live_version.number - 1), number: agent.live_version.number - 1 },
                  instructions_version: null,
                }
              : { status: "skipped", reason: NOTHING_TO_REVERT },
          ),
        ),
      );
    }),
  );
  return { requests };
}
