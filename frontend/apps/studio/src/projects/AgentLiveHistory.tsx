import { useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { formatTime } from "../settings/AuditPage";
import {
  type Agent,
  type AgentVersion,
  agentFailure,
  type LiveHistoryEntry,
  revertTarget,
  useLiveHistory,
  useRevertAgent,
} from "./agents";
import { BUTTON } from "./ProjectsPage";

const ACTIONS: Record<string, string> = {
  publish: "Published",
  revert: "Reverted",
  bulk_publish: "Bulk published",
  bulk_revert: "Bulk reverted",
};

function move(entry: LiveHistoryEntry): string {
  const to = `v${String(entry.to_version.number)}`;
  return entry.from_version ? `v${String(entry.from_version.number)} → ${to}` : to;
}

function outcome(version: AgentVersion): string {
  const pinned = version.instructions_version
    ? `with Instructions v${String(version.instructions_version.number)}`
    : "without Project Instructions";
  return `Reverted to v${String(version.number)} ${pinned}. It is now Live.`;
}

function RevertAgent({
  agent,
  organisationId,
  history,
  live,
}: {
  agent: Agent;
  organisationId: string;
  history: LiveHistoryEntry[];
  /** The Live Version, as the newest Live History entry left it. */
  live: LiveHistoryEntry["to_version"];
}) {
  const revert = useRevertAgent(organisationId, agent.project_id, agent.id);
  const [confirming, setConfirming] = useState(false);
  const target = revertTarget(live.id, history);
  const label = target && `v${String(target.number)}`;

  let control;
  if (!label) {
    control = (
      <p className="text-sm text-slate-700">
        There&apos;s no earlier Live Version to revert to: v{live.number} was the first.
      </p>
    );
  } else if (confirming) {
    control = (
      <div role="group" aria-label={`Revert to ${label}?`} className="flex flex-wrap items-center gap-2">
        <span>
          Revert to {label}? Visitors are served {label} with the Instructions it pins at once. The Draft isn&apos;t changed.
        </span>
        <button
          type="button"
          disabled={revert.isPending}
          onClick={() => {
            revert.mutate(undefined, {
              onSettled: () => {
                setConfirming(false);
              },
            });
          }}
          className="rounded bg-red-700 px-2 py-1 text-white"
        >
          {revert.isPending ? "Reverting…" : `Yes, revert to ${label}`}
        </button>
        <button
          type="button"
          onClick={() => {
            setConfirming(false);
          }}
          className="underline"
        >
          Cancel
        </button>
      </div>
    );
  } else {
    control = (
      <button
        type="button"
        onClick={() => {
          revert.reset();
          setConfirming(true);
        }}
        className={BUTTON}
      >
        Revert to {label}
      </button>
    );
  }

  return (
    <div className="space-y-2">
      {control}
      <FormError message={agentFailure(revert.error)} />
      <p role="status" className="text-sm text-slate-700">
        {revert.data ? outcome(revert.data) : ""}
      </p>
    </div>
  );
}

/**
 * The Live History timeline: every change of the Live Version, newest first, and reverting to
 * the Version that was Live before. Read-only while the Agent is archived.
 */
export function LiveHistory({ agent, organisationId, archived }: { agent: Agent; organisationId: string; archived: boolean }) {
  const history = useLiveHistory(organisationId, agent.project_id, agent.id);

  let body;
  const latest = history.data?.[0];
  if (history.isError) {
    body = <p role="alert">The Live History could not be loaded. Try again shortly.</p>;
  } else if (history.isPending) {
    body = <p>Loading the Live History…</p>;
  } else if (!latest) {
    body = <p className="text-sm text-slate-700">Nothing has been Live yet. Publish the Draft to make v1 Live.</p>;
  } else {
    body = (
      <>
        {!archived && (
          <RevertAgent agent={agent} organisationId={organisationId} history={history.data} live={latest.to_version} />
        )}
        <ol aria-label="Live History" className="space-y-1">
          {history.data.map((entry, index) => (
            <li key={`${String(index)}-${entry.occurred_at}`} className="border-t border-slate-200 py-2">
              <p>
                <span className="font-medium">{ACTIONS[entry.action]}</span> {move(entry)}
              </p>
              <p className="text-sm text-slate-700">
                {entry.actor.name} · {formatTime(entry.occurred_at)}
              </p>
            </li>
          ))}
        </ol>
      </>
    );
  }

  return (
    <section aria-labelledby="live-history-heading" className="space-y-2 rounded border border-slate-200 bg-white p-3">
      <h3 id="live-history-heading" className="font-semibold">
        Live History
      </h3>
      {body}
    </section>
  );
}
