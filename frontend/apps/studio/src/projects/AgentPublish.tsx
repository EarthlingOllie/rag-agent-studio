import { type SubmitEvent, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { AgentDiffView } from "./AgentDiff";
import { type Agent, type AgentVersion, agentFailure, publishFailure, useAgentDiff, usePublishAgent } from "./agents";
import { useInstructionsVersions } from "./instructions";
import { BUTTON, INPUT } from "./ProjectsPage";
import { useTags } from "./tags";

/** "Live v3", or "Not live" for an Agent that has never been published; and "Unpublished
 * changes" while its Draft differs from the Live Version. */
export function LiveStatus({ agent }: { agent: Agent }) {
  return (
    <>
      {agent.live_version ? (
        <span className="rounded-full bg-green-100 px-2 py-0.5 text-sm font-medium text-green-900">
          Live v{agent.live_version.number}
        </span>
      ) : (
        <span className="rounded-full bg-slate-200 px-2 py-0.5 text-sm font-medium text-slate-900">Not live</span>
      )}
      {agent.has_unpublished_changes && (
        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-sm font-medium text-amber-950">Unpublished changes</span>
      )}
    </>
  );
}

/** The Tags' names by ID, so diffs of Tag scoping read as names. */
export function useTagNames(organisationId: string, projectId: string): Record<string, string> {
  const tags = useTags(organisationId, projectId);
  return Object.fromEntries((tags.data ?? []).map((tag) => [tag.id, tag.name]));
}

/** What publishing changes: the saved Draft compared with the Live Version. */
function ChangesToPublish({ agent, organisationId }: { agent: Agent; organisationId: string }) {
  const live = agent.live_version;
  const diff = useAgentDiff(
    organisationId,
    agent.project_id,
    agent.id,
    { from: "live", to: "draft", revision: agent.draft_revision },
    live !== null,
  );
  const names = useTagNames(organisationId, agent.project_id);
  let body;
  if (!live) {
    body = <p className="text-sm text-slate-700">This is the first Version: all of the Draft&apos;s settings go live.</p>;
  } else if (diff.isPending) {
    body = <p className="text-sm text-slate-700">Comparing the Draft with the Live Version (v{live.number})…</p>;
  } else if (diff.isError) {
    body = <p className="text-sm text-slate-700">The changes could not be loaded. {agentFailure(diff.error)}</p>;
  } else {
    body = <AgentDiffView diff={diff.data} names={names} />;
  }
  return (
    <section aria-label="Changes to publish" className="space-y-2">
      <h4 className="text-sm font-semibold">{live ? `Changes from the Live Version (v${String(live.number)})` : "Changes"}</h4>
      {body}
    </section>
  );
}

function outcome(version: AgentVersion): string {
  const pinned = version.instructions_version
    ? `with Instructions v${String(version.instructions_version.number)}`
    : "without Project Instructions";
  return `Published v${String(version.number)} ${pinned}. It is now Live.`;
}

/**
 * Publishes the saved Draft as the Agent's next Version, which becomes its Live Version. The
 * Version pins the Project's Current Instructions Version, or the one the Editor chooses.
 */
export function PublishAgent({ agent, organisationId }: { agent: Agent; organisationId: string }) {
  const publish = usePublishAgent(organisationId, agent.project_id, agent.id);
  const history = useInstructionsVersions(organisationId, agent.project_id);
  const [note, setNote] = useState("");
  const [pinned, setPinned] = useState("");
  const [noteMissing, setNoteMissing] = useState(false);

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    publish.reset();
    const trimmed = note.trim();
    setNoteMissing(!trimmed);
    if (!trimmed) return;
    publish.mutate(pinned ? { note: trimmed, instructions_version_id: pinned } : { note: trimmed }, {
      onSuccess: () => {
        setNote("");
        setPinned("");
      },
    });
  }

  let options;
  if (history.isError) {
    options = <p className="text-sm text-slate-700">The Instructions Versions could not be loaded.</p>;
  } else {
    const versions = history.data?.versions ?? [];
    const current = versions.find((version) => version.id === history.data?.current_version_id);
    options = (
      <>
        <label htmlFor="publish-instructions" className="block text-sm font-medium">
          Project Instructions
        </label>
        <select
          id="publish-instructions"
          className={INPUT}
          value={pinned}
          onChange={(event) => {
            setPinned(event.target.value);
          }}
        >
          <option value="">
            {current
              ? `Current Version (v${String(current.number)})`
              : history.isPending
                ? "Current Version"
                : "None (no Instructions published)"}
          </option>
          {versions.map((version) => (
            <option key={version.id} value={version.id}>
              v{version.number} · {version.note}
            </option>
          ))}
        </select>
      </>
    );
  }

  return (
    <form aria-label="Publish" onSubmit={onSubmit} noValidate className="space-y-2 rounded border border-slate-200 bg-white p-3">
      <h3 className="font-semibold">Publish</h3>
      <p className="text-sm text-slate-700">
        Publishing freezes the saved Draft as a new Version, and Visitors are served it at once.
      </p>
      <label htmlFor="publish-note" className="block text-sm font-medium">
        Note
      </label>
      <input
        id="publish-note"
        required
        maxLength={500}
        autoComplete="off"
        className={INPUT}
        value={note}
        onChange={(event) => {
          setNote(event.target.value);
        }}
      />
      {options}
      <ChangesToPublish agent={agent} organisationId={organisationId} />
      <FormError message={noteMissing ? "Add a note of up to 500 characters." : publishFailure(publish.error)} />
      <button type="submit" className={BUTTON} disabled={publish.isPending}>
        {publish.isPending ? "Publishing…" : "Publish"}
      </button>
      <p role="status" className="text-sm text-slate-700">
        {publish.data ? outcome(publish.data) : ""}
      </p>
    </form>
  );
}
