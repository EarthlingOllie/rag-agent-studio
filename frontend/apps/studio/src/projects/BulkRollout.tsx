import { useState } from "react";

import { Badge, button, Dialog, field, Notice, Skeleton, table, text } from "../design";
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

type Target = { organisationId: string; projectId: string };
type VersionNumber = { id: string; number: number };

const v = (version: { number: number }) => `v${String(version.number)}`;
const agents = (count: number) => `${String(count)} ${count === 1 ? "Agent" : "Agents"}`;
const chip = (version: { number: number }) => <Badge kind="version" version={version.number} />;

function succeeded(outcome: BulkOutcome, verb: string): string {
  // A success always reports the Version that is now Live.
  const live = v(outcome.live_version as VersionNumber);
  const pinned = outcome.instructions_version ? ` with Instructions ${v(outcome.instructions_version)}` : " without Project Instructions";
  return `${verb} ${live}${pinned}. It is now Live.`;
}

const OUTCOME = {
  succeeded: { label: "Done", className: "text-accent-ink" },
  skipped: { label: "Skipped", className: "text-muted" },
  failed: { label: "Failed", className: "text-danger" },
} as const;

/** How many Agents succeeded, were skipped and failed, then one line per Agent: what happened, or why not. */
export function BulkResults({ result, verb }: { result: BulkResult; verb: "Published" | "Reverted to" }) {
  const count = (status: BulkOutcome["status"]) => result.results.filter((outcome) => outcome.status === status).length;
  return (
    <div className="flex flex-col gap-2">
      <p className={text.muted}>
        {`${String(count("succeeded"))} succeeded, ${String(count("skipped"))} skipped, ${String(count("failed"))} failed`}
      </p>
      <ul aria-label="Results" className="flex flex-col divide-y divide-line-soft rounded-xl border border-line">
        {result.results.map((outcome) => (
          <li key={outcome.agent_id} className="px-3.5 py-2.5 text-sm text-ink">
            <span className="font-medium">{outcome.name ?? "Unknown Agent"}</span>
            {" — "}
            <span className={OUTCOME[outcome.status].className}>
              {OUTCOME[outcome.status].label}: {outcome.status === "succeeded" ? succeeded(outcome, verb) : outcome.reason}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function why(agent: RolloutAgent, version: VersionNumber): string | undefined {
  if (!agent.live_version) return "Never published: not included. Publish it from its page first.";
  if (agent.instructions_version?.id === version.id) return `Already on ${v(version)}.`;
  return undefined;
}

/** "Live v4, Instructions v1" with version chips, or the Not live badge. */
function Pinned({ agent }: { agent: RolloutAgent }) {
  if (!agent.live_version) return <Badge kind="notLive" />;
  return (
    <span className={`inline-flex flex-wrap items-center gap-1 ${text.muted}`}>
      Live {chip(agent.live_version)}, Instructions {agent.instructions_version ? chip(agent.instructions_version) : "none"}
    </span>
  );
}

/** A checkbox per Agent; `deselected` holds the ones the Editor unticked. */
function useDeselected() {
  const [deselected, setDeselected] = useState<Set<string>>(new Set());
  const toggle = (id: string, checked: boolean) => {
    const next = new Set(deselected);
    if (checked) next.delete(id);
    else next.add(id);
    setDeselected(next);
  };
  return [deselected, toggle] as const;
}

/**
 * Rolls an Instructions Version out to the Project's Agents. Every Agent that can take it is
 * pre-selected; each new Version is built from the Agent's Live configuration, never its Draft.
 */
export function RolloutDialog({ organisationId, projectId, version, onClose }: Target & { version: VersionNumber; onClose: () => void }) {
  const rollout = useInstructionsRollout(organisationId, projectId);
  const publish = useBulkPublish(organisationId, projectId);
  const [deselected, toggle] = useDeselected();
  const failure = bulkFailure(publish.error);

  let body;
  let footer;
  if (rollout.isError) {
    body = <Notice tone="error">The Agents could not be loaded. Try again shortly.</Notice>;
  } else if (rollout.isPending) {
    body = <Skeleton label="Loading the Agents…" />;
  } else if (publish.isSuccess) {
    body = <BulkResults result={publish.data} verb="Published" />;
  }
  if (publish.isSuccess) {
    // Keyed, so React mounts a new button rather than restyling Not now in place, which would
    // fade (transition-colors) from Not now's colours to Done's at too low a contrast.
    footer = (
      <button key="done" type="button" className={button.primary} onClick={onClose}>
        Done
      </button>
    );
  } else {
    const eligible = rollout.data?.agents.filter((agent) => !why(agent, version)) ?? [];
    const selected = eligible.filter((agent) => !deselected.has(agent.id)).map((agent) => agent.id);
    if (rollout.data)
      body = (
        <>
          {failure !== undefined && <Notice tone="error">{failure}</Notice>}
          {rollout.data.agents.length === 0 ? (
            <p className={text.body}>This Project has no Agents yet.</p>
          ) : (
            <ul aria-label="Agents" className="flex flex-col divide-y divide-line-soft rounded-xl border border-line">
              {rollout.data.agents.map((agent) => {
                const reason = why(agent, version);
                return (
                  <li key={agent.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3.5 py-2.5 text-sm">
                    <label className="flex items-center gap-2 font-medium text-ink">
                      <input
                        type="checkbox"
                        className={field.checkbox}
                        disabled={reason !== undefined}
                        checked={reason === undefined && !deselected.has(agent.id)}
                        onChange={(event) => {
                          toggle(agent.id, event.currentTarget.checked);
                        }}
                      />
                      {agent.name}
                    </label>
                    <Pinned agent={agent} />
                    {agent.has_draft_changes && (
                      <span className="inline-flex items-center gap-1.5">
                        <Badge kind="draft" title="Unpublished Draft changes are not included." />
                        <span className={text.small}>changes not included</span>
                      </span>
                    )}
                    {reason && <span className={text.small}>{reason}</span>}
                  </li>
                );
              })}
            </ul>
          )}
        </>
      );
    footer = (
      <>
        <button type="button" className={button.secondary} onClick={onClose}>
          Not now
        </button>
        <button
          type="button"
          className={button.primary}
          disabled={selected.length === 0 || publish.isPending}
          onClick={() => {
            publish.mutate({ agentIds: selected, instructionsVersionId: version.id });
          }}
        >
          {publish.isPending ? "Publishing…" : `Publish to ${agents(selected.length)}`}
        </button>
      </>
    );
  }

  return (
    <Dialog
      open
      title={`Roll out Instructions ${v(version)}`}
      description={`Each selected Agent gets a new Version built from its Live configuration with Instructions ${v(version)}, and it goes Live at once. Unpublished Draft changes are not included.`}
      onClose={onClose}
      closeButton={false}
      footer={footer}
    >
      {body}
    </Dialog>
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
  const revert = useBulkRevert(organisationId, projectId);
  const [deselected, toggle] = useDeselected();
  const selected = candidates.filter((agent) => !deselected.has(agent.id)).map((agent) => agent.id);
  const failure = bulkFailure(revert.error);

  return (
    <Dialog
      open
      title={`Revert the Agents on Instructions ${v(reverted)}?`}
      description={`These Agents are Live with Instructions ${v(reverted)}. Reverting each one moves its Live Version back one step in its Live History, restoring the configuration and Instructions it ran with before.`}
      onClose={onClose}
      closeButton={false}
      footer={
        revert.isSuccess ? (
          // Keyed so it is a new button, not Not now fading into Done's colours (see RolloutDialog).
          <button key="done" type="button" className={button.primary} onClick={onClose}>
            Done
          </button>
        ) : (
          <>
            <button type="button" className={button.secondary} onClick={onClose}>
              Not now
            </button>
            <button
              type="button"
              className={button.primary}
              disabled={selected.length === 0 || revert.isPending}
              onClick={() => {
                revert.mutate(selected);
              }}
            >
              {revert.isPending ? "Reverting…" : `Revert ${agents(selected.length)}`}
            </button>
          </>
        )
      }
    >
      {revert.isSuccess ? (
        <BulkResults result={revert.data} verb="Reverted to" />
      ) : (
        <>
          {failure !== undefined && <Notice tone="error">{failure}</Notice>}
          <ul aria-label="Agents" className="flex flex-col divide-y divide-line-soft rounded-xl border border-line">
            {candidates.map((agent) => (
              <li key={agent.id} className="px-3.5 py-2.5 text-sm">
                <label className="flex items-center gap-2 font-medium text-ink">
                  <input
                    type="checkbox"
                    className={field.checkbox}
                    checked={!deselected.has(agent.id)}
                    onChange={(event) => {
                      toggle(agent.id, event.currentTarget.checked);
                    }}
                  />
                  {agent.name} (Live {v(agent.live_version)})
                </label>
              </li>
            ))}
          </ul>
        </>
      )}
    </Dialog>
  );
}

/** "N Agents behind" the Current Instructions Version, and which Version each Agent pins, as badges. */
export function AgentsBehind({ organisationId, projectId, archived, onRollOut }: Target & { archived: boolean; onRollOut: (version: VersionNumber) => void }) {
  const rollout = useInstructionsRollout(organisationId, projectId);
  if (rollout.isError) return <Notice tone="error">The Agents&apos; Instructions could not be loaded. Try again shortly.</Notice>;
  if (rollout.isPending) return <Skeleton label="Loading the Agents' Instructions" />;
  const { current_version: current, behind, agents: list } = rollout.data;
  if (list.length === 0) return <p className={text.muted}>This Project has no Agents yet.</p>;
  return (
    <div className="flex flex-col gap-3">
      {current && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className={`inline-flex flex-wrap items-center gap-1.5 ${text.body}`}>
            {agents(behind)} behind the Current Version {chip(current)}
          </p>
          {behind > 0 && !archived && (
            <button
              type="button"
              className={button.secondary}
              onClick={() => {
                onRollOut(current);
              }}
            >
              Roll out {v(current)}…
            </button>
          )}
        </div>
      )}
      <div className={table.wrap}>
        <table className={table.table}>
          <caption className="sr-only">Instructions each Agent runs with</caption>
          <thead>
            <tr>
              <th scope="col" className={table.th}>
                Agent
              </th>
              <th scope="col" className={table.th}>
                Live Version
              </th>
              <th scope="col" className={table.th}>
                Instructions
              </th>
            </tr>
          </thead>
          <tbody>
            {list.map((agent) => (
              <tr key={agent.id} className={table.row}>
                <td className={`${table.td} font-medium`}>{agent.name}</td>
                <td className={table.td}>{agent.live_version ? chip(agent.live_version) : <Badge kind="notLive" />}</td>
                <td className={table.td}>
                  <span className="inline-flex flex-wrap items-center gap-1.5">
                    {agent.live_version && (agent.instructions_version ? chip(agent.instructions_version) : <span className="text-muted">None</span>)}
                    {agent.behind && <Badge kind="instructionsBehind" />}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
