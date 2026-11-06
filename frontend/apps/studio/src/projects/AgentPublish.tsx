import { type SubmitEvent, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { type Agent, type AgentVersion, publishFailure, usePublishAgent } from "./agents";
import { useInstructionsVersions } from "./instructions";
import { BUTTON, INPUT } from "./ProjectsPage";

/** "Live v3", or "Not live" for an Agent that has never been published. */
export function LiveStatus({ agent }: { agent: Agent }) {
  return agent.live_version ? (
    <span className="rounded-full bg-green-100 px-2 py-0.5 text-sm font-medium text-green-900">
      Live v{agent.live_version.number}
    </span>
  ) : (
    <span className="rounded-full bg-slate-200 px-2 py-0.5 text-sm font-medium text-slate-900">Not live</span>
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
