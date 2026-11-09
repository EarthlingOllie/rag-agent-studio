import { useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { button, ConfirmDialog, Icon, Menu, type MenuItem, Skeleton, surface, text } from "../design";
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

/**
 * Reverting to the Version that was Live before the current one, after a confirmation. The ⋯ menu
 * on the Live Version's entry offers it; this shows the confirmation, the outcome and any refusal.
 */
function useRevert(agent: Agent, organisationId: string, history: LiveHistoryEntry[], live: LiveHistoryEntry["to_version"]) {
  const revert = useRevertAgent(organisationId, agent.project_id, agent.id);
  const [confirming, setConfirming] = useState(false);
  const target = revertTarget(live.id, history);
  const label = target && `v${String(target.number)}`;
  const item: MenuItem | null = label
    ? {
        label: `Revert to ${label}`,
        onSelect: () => {
          revert.reset();
          setConfirming(true);
        },
      }
    : null;
  const ui = (
    <>
      {!label && <p className={text.muted}>There&apos;s no earlier Live Version to revert to: v{live.number} was the first.</p>}
      <FormError message={agentFailure(revert.error)} />
      <p role="status" className={text.muted}>
        {revert.data ? outcome(revert.data) : ""}
      </p>
      <ConfirmDialog
        open={confirming}
        title={`Revert to ${label as string}?`}
        confirmLabel={revert.isPending ? "Reverting…" : `Yes, revert to ${label as string}`}
        busy={revert.isPending}
        onConfirm={() => {
          revert.mutate(undefined, {
            onSettled: () => {
              setConfirming(false);
            },
          });
        }}
        onCancel={() => {
          setConfirming(false);
        }}
      >
        Visitors are served {label} with the Instructions it pins at once. The Draft isn&apos;t changed.
      </ConfirmDialog>
    </>
  );
  return { item, ui };
}

function Timeline({
  agent,
  organisationId,
  history,
  archived,
}: {
  agent: Agent;
  organisationId: string;
  history: LiveHistoryEntry[];
  archived: boolean;
}) {
  const live = (history[0] as LiveHistoryEntry).to_version;
  const revert = useRevert(agent, organisationId, history, live);
  return (
    <>
      {!archived && revert.ui}
      <ol aria-label="Live History" className="flex flex-col">
        {history.map((entry, index) => (
          <li key={`${String(index)}-${entry.occurred_at}`} className="relative flex gap-4 pb-5 last:pb-0">
            {/* The rail and the dot: the Live Version's dot is the accent. */}
            <span aria-hidden="true" className="relative flex w-3 shrink-0 justify-center">
              {index < history.length - 1 && <span className="absolute top-3 -bottom-5 w-px bg-line" />}
              <span className={`mt-1.5 size-2.5 rounded-full ${index === 0 ? "bg-accent" : "border border-field bg-surface"}`} />
            </span>
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <p className="text-ink">
                <span className="font-medium">{ACTIONS[entry.action]}</span> <span className={text.mono}>{move(entry)}</span>
              </p>
              <p className={text.small}>
                {entry.actor.name} · {formatTime(entry.occurred_at)}
              </p>
            </div>
            {index === 0 && !archived && revert.item && (
              <Menu
                label={<Icon name="more" />}
                triggerLabel="Actions for the Live Version"
                align="end"
                triggerClassName={button.iconBare}
                items={[revert.item]}
              />
            )}
          </li>
        ))}
      </ol>
    </>
  );
}

/**
 * The Live History timeline: every change of the Live Version, newest first, and reverting to
 * the Version that was Live before, from the Live Version's ⋯ menu. Read-only while the Agent is
 * archived.
 */
export function LiveHistory({ agent, organisationId, archived }: { agent: Agent; organisationId: string; archived: boolean }) {
  const history = useLiveHistory(organisationId, agent.project_id, agent.id);

  let body;
  if (history.isError) {
    body = <p role="alert">The Live History could not be loaded. Try again shortly.</p>;
  } else if (history.isPending) {
    body = <Skeleton label="Loading the Live History" />;
  } else if (history.data.length === 0) {
    body = <p className={text.muted}>Nothing has been Live yet. Publish the Draft to make v1 Live.</p>;
  } else {
    body = <Timeline agent={agent} organisationId={organisationId} history={history.data} archived={archived} />;
  }

  return (
    <section aria-labelledby="live-history-heading" className={`${surface.panel} flex flex-col gap-4`}>
      <h2 id="live-history-heading" className={text.subheading}>
        Live History
      </h2>
      {body}
    </section>
  );
}
