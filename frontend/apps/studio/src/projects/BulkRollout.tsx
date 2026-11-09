import { useId, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import {
  type BulkOutcome,
  type BulkResult,
  type BulkRevertCandidate,
  bulkFailure,
  type RolloutAgent,
  useBulkPublish,
  useBulkRevert,
  useInstructionsRollout,
} from "./bulk";
import { BUTTON } from "./ProjectsPage";

type Target = { organisationId: string; projectId: string };
type VersionNumber = { id: string; number: number };

const v = (version: { number: number }) => `v${String(version.number)}`;
const agents = (count: number) => `${String(count)} ${count === 1 ? "Agent" : "Agents"}`;

function succeeded(outcome: BulkOutcome, verb: string): string {
  // A success always reports the Version that is now Live.
  const live = v(outcome.live_version as VersionNumber);
  const pinned = outcome.instructions_version ? ` with Instructions ${v(outcome.instructions_version)}` : " without Project Instructions";
  return `${verb} ${live}${pinned}. It is now Live.`;
}

/** One line per Agent: what happened to it, or why it was skipped or failed. */
export function BulkResults({ result, verb }: { result: BulkResult; verb: "Published" | "Reverted to" }) {
  const label = { succeeded: "Done", skipped: "Skipped", failed: "Failed" };
  return (
    <ul aria-label="Results" className="space-y-1">
      {result.results.map((outcome) => (
        <li key={outcome.agent_id} className="text-sm">
          <span className="font-medium">{outcome.name ?? "Unknown Agent"}</span>
          {" — "}
          <span className={outcome.status === "failed" ? "text-danger" : undefined}>
            {label[outcome.status]}: {outcome.status === "succeeded" ? succeeded(outcome, verb) : outcome.reason}
          </span>
        </li>
      ))}
    </ul>
  );
}

function why(agent: RolloutAgent, version: VersionNumber): string | undefined {
  if (!agent.live_version) return "Never published: not included. Publish it from its page first.";
  if (agent.instructions_version?.id === version.id) return `Already on ${v(version)}.`;
  return undefined;
}

function pinnedLabel(agent: RolloutAgent): string {
  if (!agent.live_version) return "Not live";
  return `Live ${v(agent.live_version)}, Instructions ${agent.instructions_version ? v(agent.instructions_version) : "none"}`;
}

function DraftBadge() {
  return (
    <span className="rounded-full bg-flag-soft px-2 py-0.5 text-xs font-medium text-flag">
      Unpublished Draft changes (not included)
    </span>
  );
}

/**
 * Rolls an Instructions Version out to the Project's Agents. Every Agent that can take it is
 * pre-selected; each new Version is built from the Agent's Live configuration, never its Draft.
 */
export function RolloutDialog({ organisationId, projectId, version, onClose }: Target & { version: VersionNumber; onClose: () => void }) {
  const headingId = useId();
  const rollout = useInstructionsRollout(organisationId, projectId);
  const publish = useBulkPublish(organisationId, projectId);
  const [deselected, setDeselected] = useState<Set<string>>(new Set());

  let body;
  if (rollout.isError) {
    body = <p role="alert">The Agents could not be loaded. Try again shortly.</p>;
  } else if (rollout.isPending) {
    body = <p role="status">Loading the Agents…</p>;
  } else if (publish.isSuccess) {
    body = (
      <>
        <BulkResults result={publish.data} verb="Published" />
        <button type="button" className={BUTTON} onClick={onClose}>
          Done
        </button>
      </>
    );
  } else {
    const eligible = rollout.data.agents.filter((agent) => !why(agent, version));
    const selected = eligible.filter((agent) => !deselected.has(agent.id)).map((agent) => agent.id);
    body = (
      <>
        <p className="text-sm text-muted">
          Each selected Agent gets a new Version built from its Live configuration with Instructions {v(version)}, and it goes Live at
          once. Unpublished Draft changes are not included.
        </p>
        <FormError message={bulkFailure(publish.error)} />
        {rollout.data.agents.length === 0 ? (
          <p>This Project has no Agents yet.</p>
        ) : (
          <ul aria-label="Agents" className="space-y-2">
            {rollout.data.agents.map((agent) => {
              const reason = why(agent, version);
              return (
                <li key={agent.id} className="flex flex-wrap items-center gap-2">
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      disabled={reason !== undefined}
                      checked={reason === undefined && !deselected.has(agent.id)}
                      onChange={(event) => {
                        const next = new Set(deselected);
                        if (event.currentTarget.checked) next.delete(agent.id);
                        else next.add(agent.id);
                        setDeselected(next);
                      }}
                    />
                    {agent.name}
                  </label>
                  <span className="text-sm text-muted">{pinnedLabel(agent)}</span>
                  {agent.has_draft_changes && <DraftBadge />}
                  {reason && <span className="text-sm text-muted">{reason}</span>}
                </li>
              );
            })}
          </ul>
        )}
        <div className="flex gap-2">
          <button
            type="button"
            className={BUTTON}
            disabled={selected.length === 0 || publish.isPending}
            onClick={() => {
              publish.mutate({ agentIds: selected, instructionsVersionId: version.id });
            }}
          >
            {publish.isPending ? "Publishing…" : `Publish to ${agents(selected.length)}`}
          </button>
          <button type="button" className="underline" onClick={onClose}>
            Not now
          </button>
        </div>
      </>
    );
  }

  return (
    <section role="dialog" aria-labelledby={headingId} className="space-y-3 rounded border border-field bg-surface p-4">
      <h3 id={headingId} className="font-semibold">
        Roll out Instructions {v(version)}
      </h3>
      {body}
    </section>
  );
}

/** After reverting the Instructions, offers to bulk-revert the Agents still pinned to the reverted Version. */
export function BulkRevertOffer({
  organisationId,
  projectId,
  reverted,
  candidates,
  onClose,
}: Target & { reverted: { number: number }; candidates: BulkRevertCandidate[]; onClose: () => void }) {
  const headingId = useId();
  const revert = useBulkRevert(organisationId, projectId);
  const [deselected, setDeselected] = useState<Set<string>>(new Set());
  const selected = candidates.filter((agent) => !deselected.has(agent.id)).map((agent) => agent.id);

  return (
    <section role="dialog" aria-labelledby={headingId} className="space-y-3 rounded border border-field bg-surface p-4">
      <h3 id={headingId} className="font-semibold">
        Revert the Agents on Instructions {v(reverted)}?
      </h3>
      {revert.isSuccess ? (
        <>
          <BulkResults result={revert.data} verb="Reverted to" />
          <button type="button" className={BUTTON} onClick={onClose}>
            Done
          </button>
        </>
      ) : (
        <>
          <p className="text-sm text-muted">
            These Agents are Live with Instructions {v(reverted)}. Reverting each one moves its Live Version back one step in its Live
            History, restoring the configuration and Instructions it ran with before.
          </p>
          <FormError message={bulkFailure(revert.error)} />
          <ul aria-label="Agents" className="space-y-2">
            {candidates.map((agent) => (
              <li key={agent.id}>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={!deselected.has(agent.id)}
                    onChange={(event) => {
                      const next = new Set(deselected);
                      if (event.currentTarget.checked) next.delete(agent.id);
                      else next.add(agent.id);
                      setDeselected(next);
                    }}
                  />
                  {agent.name} (Live {v(agent.live_version)})
                </label>
              </li>
            ))}
          </ul>
          <div className="flex gap-2">
            <button
              type="button"
              className={BUTTON}
              disabled={selected.length === 0 || revert.isPending}
              onClick={() => {
                revert.mutate(selected);
              }}
            >
              {revert.isPending ? "Reverting…" : `Revert ${agents(selected.length)}`}
            </button>
            <button type="button" className="underline" onClick={onClose}>
              Not now
            </button>
          </div>
        </>
      )}
    </section>
  );
}

/** "N Agents behind" the Current Instructions Version, and which Version each Agent pins. */
export function AgentsBehind({ organisationId, projectId, archived, onRollOut }: Target & { archived: boolean; onRollOut: (version: VersionNumber) => void }) {
  const rollout = useInstructionsRollout(organisationId, projectId);
  if (rollout.isError) return <p role="alert">The Agents' Instructions could not be loaded. Try again shortly.</p>;
  if (rollout.isPending) return <p>Loading the Agents' Instructions…</p>;
  const { current_version: current, behind, agents: list } = rollout.data;
  if (list.length === 0) return <p className="text-muted">This Project has no Agents yet.</p>;
  return (
    <div className="space-y-2">
      {current && (
        <p className="flex flex-wrap items-center gap-3">
          <span>
            {agents(behind)} behind the Current Version ({v(current)}).
          </span>
          {behind > 0 && !archived && (
            <button
              type="button"
              className={BUTTON}
              onClick={() => {
                onRollOut(current);
              }}
            >
              Roll out {v(current)}…
            </button>
          )}
        </p>
      )}
      <table className="text-sm">
        <caption className="sr-only">Instructions each Agent runs with</caption>
        <thead>
          <tr>
            <th scope="col" className="pr-4 text-left">
              Agent
            </th>
            <th scope="col" className="pr-4 text-left">
              Live Version
            </th>
            <th scope="col" className="pr-4 text-left">
              Instructions
            </th>
          </tr>
        </thead>
        <tbody>
          {list.map((agent) => (
            <tr key={agent.id}>
              <td className="pr-4">{agent.name}</td>
              <td className="pr-4">{agent.live_version ? v(agent.live_version) : "Not live"}</td>
              <td className="pr-4">
                {agent.live_version && (agent.instructions_version ? v(agent.instructions_version) : "None")}
                {agent.behind && " (behind)"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
