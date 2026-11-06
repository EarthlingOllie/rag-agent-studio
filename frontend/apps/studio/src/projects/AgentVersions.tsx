import { useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { AgentDiffView } from "./AgentDiff";
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
import { BUTTON, INPUT } from "./ProjectsPage";

type DraftProps = { agent: Agent; organisationId: string; onReplaced: () => void };

/**
 * Discards the Draft's unpublished changes: the Live Version's settings go back in the Draft,
 * after the Editor confirms. Shown while the Draft differs from the Live Version.
 */
export function DiscardDraft({ agent, organisationId, onReplaced }: DraftProps) {
  const replace = useReplaceDraft(organisationId, agent.project_id, agent.id);
  const [confirming, setConfirming] = useState(false);
  const live = agent.live_version;
  if (!live || (!agent.has_unpublished_changes && !replace.error)) return null;
  return (
    <div className="space-y-2">
      <FormError message={draftChangeFailure(replace.error)} />
      {confirming ? (
        <div role="group" aria-label="Discard the Draft" className="space-y-2 rounded border border-slate-200 bg-white p-3 text-sm">
          <p>The Draft&apos;s unpublished changes will be lost, and it goes back to the settings of the Live Version (v{live.number}).</p>
          <div className="flex gap-2">
            <button
              type="button"
              className={BUTTON}
              disabled={replace.isPending}
              onClick={() => {
                replace.mutate(
                  { versionId: "live", baseRevision: agent.draft_revision },
                  {
                    onSuccess: onReplaced,
                    onSettled: () => {
                      setConfirming(false);
                    },
                  },
                );
              }}
            >
              Yes, discard the changes
            </button>
            <button
              type="button"
              className={BUTTON}
              onClick={() => {
                setConfirming(false);
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          className={BUTTON}
          onClick={() => {
            replace.reset();
            setConfirming(true);
          }}
        >
          Discard Draft
        </button>
      )}
    </div>
  );
}

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
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      <select
        id={id}
        className={INPUT}
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
  let body;
  if (diff.isPending) body = <p className="text-sm text-slate-700">Comparing…</p>;
  else if (diff.isError) body = <p className="text-sm text-slate-700">The comparison could not be loaded. {agentFailure(diff.error)}</p>;
  else body = <AgentDiffView diff={diff.data} names={names} />;
  return (
    <section aria-labelledby="compare-heading" className="space-y-2">
      <h4 id="compare-heading" className="text-sm font-semibold">
        Compare
      </h4>
      <div className="grid gap-2 sm:grid-cols-2">
        {picker("compare-from", "From", from, setFrom)}
        {picker("compare-to", "To", to, setTo)}
      </div>
      {body}
    </section>
  );
}

function StartDraft({
  agent,
  organisationId,
  version,
  onReplaced,
}: DraftProps & { version: AgentVersion }) {
  const replace = useReplaceDraft(organisationId, agent.project_id, agent.id);
  const [confirming, setConfirming] = useState(false);
  const label = `Start Draft from v${String(version.number)}`;
  return (
    <div className="space-y-1">
      <FormError message={draftChangeFailure(replace.error)} />
      {confirming ? (
        <div role="group" aria-label={label} className="flex flex-wrap items-center gap-2 text-sm">
          <span>The Draft will be replaced by v{version.number}&apos;s settings. Nothing is published.</span>
          <button
            type="button"
            className={BUTTON}
            disabled={replace.isPending}
            onClick={() => {
              replace.mutate(
                { versionId: version.id, baseRevision: agent.draft_revision },
                {
                  onSuccess: onReplaced,
                  onSettled: () => {
                    setConfirming(false);
                  },
                },
              );
            }}
          >
            Yes, replace the Draft
          </button>
          <button
            type="button"
            className={BUTTON}
            onClick={() => {
              setConfirming(false);
            }}
          >
            Cancel
          </button>
        </div>
      ) : (
        <button
          type="button"
          className="text-sm text-slate-900 underline"
          onClick={() => {
            replace.reset();
            setConfirming(true);
          }}
        >
          {label}
        </button>
      )}
    </div>
  );
}

/**
 * The Agent's Versions, newest first: number, note, author, time, pinned Instructions and which
 * is Live. Any two (or the Draft) can be compared, and the Draft can be started from any of
 * them. An archived Agent's Versions can be read and compared but start no Draft.
 */
export function AgentVersions({ agent, organisationId, onReplaced }: DraftProps) {
  const found = useAgentVersions(organisationId, agent.project_id, agent.id);
  const archived = agent.archived_at !== null;
  let body;
  if (found.isPending) {
    body = <p className="text-sm text-slate-700">Loading the Versions…</p>;
  } else if (found.isError) {
    body = <p className="text-sm text-slate-700">The Versions could not be loaded.</p>;
  } else if (found.data.versions.length === 0) {
    body = <p className="text-sm text-slate-700">No Versions yet. Publishing the Draft makes v1.</p>;
  } else {
    const { versions, live_version_id: liveId } = found.data;
    body = (
      <>
        <ol aria-label="Versions" className="space-y-2">
          {versions.map((version) => (
            <li key={version.id} className="space-y-1 rounded border border-slate-200 bg-white p-2 text-sm">
              <p>
                <span className="font-semibold">v{version.number}</span>
                {version.id === liveId && <span className="ml-2 rounded-full bg-green-100 px-2 text-green-900">Live</span>} · {version.note}
              </p>
              <p className="text-slate-700">
                {version.author.name} · {new Date(version.created_at).toLocaleString()} ·{" "}
                {version.instructions_version ? `Instructions v${String(version.instructions_version.number)}` : "No Project Instructions"}
              </p>
              {!archived && <StartDraft agent={agent} organisationId={organisationId} version={version} onReplaced={onReplaced} />}
            </li>
          ))}
        </ol>
        <Compare agent={agent} organisationId={organisationId} versions={versions} liveId={liveId} />
      </>
    );
  }
  return (
    <section aria-labelledby="versions-heading" className="space-y-2 rounded border border-slate-200 bg-white p-3">
      <h3 id="versions-heading" className="font-semibold">
        Versions
      </h3>
      {body}
    </section>
  );
}
