import { type SubmitEvent, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { Badge, button, field, text } from "../design";
import { AgentDiffView } from "./AgentDiff";
import { type Agent, type AgentVersion, agentFailure, publishFailure, useAgentDiff, usePublishAgent } from "./agents";
import { useInstructionsVersions } from "./instructions";
import { useTags } from "./tags";

/** Live with its Version chip, or Not live for an Agent that has never been published; Draft while
 * its Draft differs from the Live Version; and its alert badges. */
export function LiveStatus({ agent }: { agent: Agent }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      {agent.live_version ? (
        <>
          <Badge kind="live" />
          <Badge kind="version" version={agent.live_version.number} />
        </>
      ) : (
        <Badge kind="notLive" />
      )}
      {agent.has_unpublished_changes && <Badge kind="draft" title="The Draft has changes that aren't published yet." />}
      {agent.budget_exhausted && (
        <Badge kind="budgetSpent" title="Today's Token Budget is spent, so Visitors see the unavailable text until midnight UTC." />
      )}
      {agent.block_rate_alert && (
        <span
          title="In the last hour, the input Guardrail blocked an unusual share of Visitor messages, as in an attack. Review the blocked Conversations."
          className="inline-flex items-center rounded-full bg-danger-soft px-2.5 py-0.5 text-xs font-medium whitespace-nowrap text-danger"
        >
          Block rate spike
        </span>
      )}
    </span>
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
    body = <p className="text-sm text-muted">This is the first Version: all of the Draft&apos;s settings go live.</p>;
  } else if (diff.isPending) {
    body = <p className="text-sm text-muted">Comparing the Draft with the Live Version (v{live.number})…</p>;
  } else if (diff.isError) {
    body = <p className="text-sm text-muted">The changes could not be loaded. {agentFailure(diff.error)}</p>;
  } else {
    body = <AgentDiffView diff={diff.data} names={names} />;
  }
  return (
    <section aria-label="Changes to publish" className="flex flex-col gap-2">
      <h3 className="text-sm font-semibold text-ink">{live ? `Changes from the Live Version (v${String(live.number)})` : "Changes"}</h3>
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
    options = <p className="text-sm text-muted">The Instructions Versions could not be loaded.</p>;
  } else {
    const versions = history.data?.versions ?? [];
    const current = versions.find((version) => version.id === history.data?.current_version_id);
    options = (
      <>
        <label htmlFor="publish-instructions" className={field.label}>
          Project Instructions
        </label>
        <select
          id="publish-instructions"
          className={field.select}
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
    <form aria-label="Publish" onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      <p className={text.muted}>Publishing freezes the saved Draft as a new Version, and Visitors are served it at once.</p>
      <div>
        <label htmlFor="publish-note" className={field.label}>
          Note
        </label>
        <input
          id="publish-note"
          required
          maxLength={500}
          autoComplete="off"
          className={field.input}
        value={note}
          onChange={(event) => {
            setNote(event.target.value);
          }}
        />
      </div>
      <div>{options}</div>
      <ChangesToPublish agent={agent} organisationId={organisationId} />
      <FormError message={noteMissing ? "Add a note of up to 500 characters." : publishFailure(publish.error)} />
      <div className="flex justify-end">
        <button type="submit" className={button.primary} disabled={publish.isPending}>
          {publish.isPending ? "Publishing…" : "Publish"}
        </button>
      </div>
      <p role="status" className={text.muted}>
        {publish.data ? outcome(publish.data) : ""}
      </p>
    </form>
  );
}
