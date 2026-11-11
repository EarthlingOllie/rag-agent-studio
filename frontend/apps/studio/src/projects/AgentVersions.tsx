import { useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { Badge, button, ConfirmDialog, field, Icon, Menu, Skeleton, surface, text } from "../design";
import { AgentDiffView, retrievalModeName } from "./AgentDiff";
import { useTagNames } from "./AgentPublish";
import {
  type Agent,
  type AgentVersion,
  type DiffSide,
  agentFailure,
  draftChangeFailure,
  useAgentDiff,
  useAgentVersions,
  useReplaceDraft,
} from "./agents";

type DraftProps = { agent: Agent; organisationId: string; onReplaced: () => void };

function sideName(side: DiffSide, versions: AgentVersion[], liveId: string | null): string {
  if (side === "draft") return "Draft";
  const found = versions.find((version) => version.id === side) as AgentVersion;
  return `v${String(found.number)}${found.id === liveId ? " (Live)" : ""}`;
}

function Compare({
  agent,
  organisationId,
  versions,
  liveId,
}: {
  agent: Agent;
  organisationId: string;
  versions: AgentVersion[];
  liveId: string | null;
}) {
  // By default, what the Draft changes from the Live Version.
  const [from, setFrom] = useState<DiffSide>(liveId ?? "draft");
  const [to, setTo] = useState<DiffSide>("draft");
  const diff = useAgentDiff(organisationId, agent.project_id, agent.id, { from, to, revision: agent.draft_revision });
  const names = useTagNames(organisationId, agent.project_id);
  const sides: DiffSide[] = ["draft", ...versions.map((version) => version.id)];
  const picker = (id: string, label: string, value: DiffSide, onChange: (side: DiffSide) => void) => (
    <div>
      <label htmlFor={id} className={field.label}>
        {label}
      </label>
      <select
        id={id}
        className={field.select}
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      >
        {sides.map((side) => (
          <option key={side} value={side}>
            {sideName(side, versions, liveId)}
          </option>
        ))}
      </select>
    </div>
  );
  // Between two Versions, the Diff shows each one's Retrieval Mode.
  const mode = (side: DiffSide) => versions.find((version) => version.id === side)?.config.retrieval.mode;
  const [fromMode, toMode] = [mode(from), mode(to)];
  const modes = fromMode && toMode ? { from: fromMode, to: toMode } : undefined;
  let body;
  if (diff.isPending) body = <p className={text.muted}>Comparing…</p>;
  else if (diff.isError) body = <p className={text.muted}>The comparison could not be loaded. {agentFailure(diff.error)}</p>;
  else body = <AgentDiffView diff={diff.data} names={names} modes={modes} />;
  return (
    <section aria-labelledby="compare-heading" className={`${surface.panel} flex flex-col gap-4`}>
      <h2 id="compare-heading" className={text.subheading}>
        Compare
      </h2>
      <div className="grid gap-3 sm:grid-cols-2">
        {picker("compare-from", "From", from, setFrom)}
        {picker("compare-to", "To", to, setTo)}
      </div>
      {body}
    </section>
  );
}

/**
 * The Agent's Versions, newest first: number, note, author, time, pinned Instructions and which
 * is Live. Each Version's ⋯ menu starts the Draft from it, after a confirmation. Any two (or the
 * Draft) can be compared. An archived Agent's Versions can be read and compared but start no Draft.
 */
export function AgentVersions({ agent, organisationId, onReplaced }: DraftProps) {
  const found = useAgentVersions(organisationId, agent.project_id, agent.id);
  const replace = useReplaceDraft(organisationId, agent.project_id, agent.id);
  const [starting, setStarting] = useState<AgentVersion | null>(null);
  const archived = agent.archived_at !== null;
  let body;
  if (found.isPending) {
    body = <Skeleton label="Loading the Versions" />;
  } else if (found.isError) {
    body = <p className={text.muted}>The Versions could not be loaded.</p>;
  } else if (found.data.versions.length === 0) {
    body = <p className={text.muted}>No Versions yet. Publishing the Draft makes v1.</p>;
  } else {
    const { versions, live_version_id: liveId } = found.data;
    body = (
      <ol aria-label="Versions" className="flex flex-col divide-y divide-line-soft">
        {versions.map((version) => (
          <li key={version.id} className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
            <div className="flex min-w-0 flex-1 flex-col gap-1 text-sm">
              <p className="flex flex-wrap items-center gap-2 text-ink">
                <Badge kind="version" version={version.number} />
                {version.id === liveId && <Badge kind="live" />}
                <span>{version.note}</span>
              </p>
              <p className={text.small}>
                {version.author.name} · {new Date(version.created_at).toLocaleString()} ·{" "}
                {version.instructions_version ? `Instructions v${String(version.instructions_version.number)}` : "No Project Instructions"} ·{" "}
                {`Retrieval Mode: ${retrievalModeName(version.config.retrieval.mode)}`}
              </p>
            </div>
            {!archived && (
              <Menu
                label={<Icon name="more" />}
                triggerLabel={`Actions for v${String(version.number)}`}
                align="end"
                triggerClassName={button.iconBare}
                items={[
                  {
                    label: `Start Draft from v${String(version.number)}`,
                    onSelect: () => {
                      replace.reset();
                      setStarting(version);
                    },
                  },
                ]}
              />
            )}
          </li>
        ))}
      </ol>
    );
  }
  return (
    <>
      <section aria-labelledby="versions-heading" className={`${surface.panel} flex flex-col gap-4`}>
        <h2 id="versions-heading" className={text.subheading}>
          Versions
        </h2>
        <FormError message={draftChangeFailure(replace.error)} />
        {body}
        {starting && (
          <ConfirmDialog
            open
            title={`Start Draft from v${String(starting.number)}?`}
            confirmLabel="Yes, replace the Draft"
            busy={replace.isPending}
            onConfirm={() => {
              replace.mutate(
                { versionId: starting.id, baseRevision: agent.draft_revision },
                {
                  onSuccess: onReplaced,
                  onSettled: () => {
                    setStarting(null);
                  },
                },
              );
            }}
            onCancel={() => {
              setStarting(null);
            }}
          >
            The Draft will be replaced by v{starting.number}&apos;s settings. Nothing is published.
          </ConfirmDialog>
        )}
      </section>
      {found.data && found.data.versions.length > 0 && (
        <Compare agent={agent} organisationId={organisationId} versions={found.data.versions} liveId={found.data.live_version_id} />
      )}
    </>
  );
}
