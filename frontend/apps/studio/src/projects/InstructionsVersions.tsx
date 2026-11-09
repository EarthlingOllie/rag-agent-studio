import { type SubmitEvent, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { formatTime } from "../settings/AuditPage";
import { TextDiff } from "./AgentDiff";
import {
  type DraftInstructions,
  type InstructionsDiff,
  type InstructionsReverted,
  type InstructionsVersion,
  useInstructions,
  useInstructionsDiff,
  useInstructionsVersions,
  useIsLatestInstructionsChange,
  usePublishInstructions,
  useRevertInstructions,
  StaleInstructionsError,
  versionFailure,
} from "./instructions";
import { BUTTON, INPUT } from "./ProjectsPage";

type Target = { organisationId: string; projectId: string };

/**
 * Publishes the Draft as written in the editor (`markdown()`, made on revision `baseRevision()`),
 * with a note, as the next Version, then hands it to `onPublished`. A Draft someone else changed
 * since is not published: `onStale` gets their Draft.
 */
export function PublishInstructionsForm({
  organisationId,
  projectId,
  markdown,
  baseRevision,
  onSaved,
  onStale,
  onPublished,
}: Target & {
  markdown: () => string;
  baseRevision: () => number;
  onSaved: (revision: number) => void;
  onStale: (latest: DraftInstructions) => void;
  onPublished: (version: InstructionsVersion) => void;
}) {
  const publish = usePublishInstructions(organisationId, projectId);
  const latest = useIsLatestInstructionsChange(organisationId, projectId, publish.submittedAt);

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const note = new FormData(form).get("note") as string;
    publish.mutate(
      { markdown: markdown(), note, baseRevision: baseRevision(), onSaved },
      {
        onSuccess: (version) => {
          form.reset();
          onPublished(version);
        },
        onError: (error) => {
          if (error instanceof StaleInstructionsError) onStale(error.latest);
        },
      },
    );
  }

  return (
    <form aria-label="Publish Instructions" onSubmit={onSubmit} className="space-y-2 rounded border border-field p-3">
      <FormError message={latest && !(publish.error instanceof StaleInstructionsError) ? versionFailure(publish.error) : undefined} />
      <label className="block">
        Note
        <input name="note" required maxLength={500} className={INPUT} />
      </label>
      <p className="text-sm text-muted">
        Publishing saves the Draft and freezes it as a new Version, which becomes the Current Version that Agents are published with.
      </p>
      <div className="flex items-center gap-3">
        <button type="submit" disabled={publish.isPending} className={BUTTON}>
          {publish.isPending ? "Publishing…" : "Publish Instructions"}
        </button>
        {publish.isSuccess && latest && (
          <span role="status" className="text-sm text-muted">
            Published v{publish.data.number}
          </span>
        )}
      </div>
    </form>
  );
}

function VersionItem({ version, current }: { version: InstructionsVersion; current: boolean }) {
  return (
    <li aria-label={`v${String(version.number)}`} className="space-y-1 border-t border-line py-2">
      <div className="flex items-center gap-2">
        <span className="font-semibold">v{version.number}</span>
        {current && <span className="rounded bg-accent-soft px-2 text-sm text-accent-ink">Current</span>}
      </div>
      <p>{version.note}</p>
      <p className="text-sm text-muted">
        {version.author ? version.author.name : "No author"} · {formatTime(version.created_at)}
      </p>
      <details>
        <summary className="cursor-pointer text-sm underline">Show the Instructions</summary>
        <pre className="mt-1 whitespace-pre-wrap rounded bg-canvas p-2 text-sm">{version.markdown || "(empty)"}</pre>
      </details>
    </li>
  );
}

/** Compares any two Instructions Versions, or one with the saved Draft, line by line. */
function CompareInstructions({ organisationId, projectId, versions, currentId }: Target & { versions: InstructionsVersion[]; currentId: string | null }) {
  const draft = useInstructions(organisationId, projectId);
  // By default, what publishing the saved Draft would change.
  const [from, setFrom] = useState(currentId ?? "draft");
  const [to, setTo] = useState("draft");
  const diff = useInstructionsDiff(organisationId, projectId, { from, to, draft: draft.data?.revision });
  const name = (side: InstructionsDiff["from"]) => (side.version ? `v${String(side.version.number)}` : "the Draft");
  const picker = (id: string, label: string, value: string, onChange: (side: string) => void) => (
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
        <option value="draft">Draft (saved)</option>
        {versions.map((version) => (
          <option key={version.id} value={version.id}>
            v{version.number}
            {version.id === currentId ? " (Current)" : ""}
          </option>
        ))}
      </select>
    </div>
  );
  let body;
  if (diff.isPending) body = <p className="text-sm text-muted">Comparing…</p>;
  else if (diff.isError) body = <p className="text-sm text-muted">The comparison could not be loaded. Try again shortly.</p>;
  else if (diff.data.lines.every((line) => line.op === "equal"))
    body = (
      <p className="text-sm text-muted">
        No differences: {name(diff.data.from)} and {name(diff.data.to)} are the same.
      </p>
    );
  else body = <TextDiff lines={diff.data.lines} label={`Changes from ${name(diff.data.from)} to ${name(diff.data.to)}`} />;
  return (
    <section aria-labelledby="compare-instructions-heading" className="space-y-2">
      <h3 id="compare-instructions-heading" className="font-semibold">
        Compare
      </h3>
      <div className="grid gap-2 sm:grid-cols-2">
        {picker("compare-instructions-from", "From", from, setFrom)}
        {picker("compare-instructions-to", "To", to, setTo)}
      </div>
      {body}
    </section>
  );
}

/** The Version history, the Current Version and reverting it. Read-only while the Project is archived. */
export function InstructionsVersions({
  organisationId,
  projectId,
  archived,
  onReverted,
}: Target & { archived: boolean; onReverted: (reverted: InstructionsReverted) => void }) {
  const versions = useInstructionsVersions(organisationId, projectId);
  const revert = useRevertInstructions(organisationId, projectId);
  const latest = useIsLatestInstructionsChange(organisationId, projectId, revert.submittedAt);
  const [confirming, setConfirming] = useState(false);

  if (versions.isError) return <p role="alert">The Versions could not be loaded. Try again shortly.</p>;
  if (versions.isPending) return <p>Loading the Versions…</p>;

  const { current_version_id: currentId, versions: list } = versions.data;
  const current = list.find((version) => version.id === currentId);
  const previous = current && list.find((version) => version.id === current.previous_version_id);

  let revertControl = null;
  if (previous && !archived) {
    const label = `v${String(previous.number)}`;
    revertControl = confirming ? (
      <div role="group" aria-label={`Revert to ${label}?`} className="flex flex-wrap items-center gap-2">
        <span>
          Revert the Current Version to {label}? Agents published from now on use {label}. The Draft isn't changed.
        </span>
        <button
          type="button"
          onClick={() => {
            revert.mutate(undefined, {
              onSuccess: onReverted,
              onSettled: () => {
                setConfirming(false);
              },
            });
          }}
          disabled={revert.isPending}
          className="rounded bg-danger px-2 py-1 text-on-danger"
        >
          Yes, revert to {label}
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
    ) : (
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
      <p>
        {current
          ? `Current Version: v${String(current.number)}.`
          : "Not published yet. Publish the Draft to make v1, the Current Version."}
      </p>
      <FormError message={latest ? versionFailure(revert.error) : undefined} />
      {revert.isSuccess && latest && (
        <p role="status" className="text-sm text-muted">
          Reverted to v{revert.data.number}
        </p>
      )}
      {revertControl}
      {list.length > 0 && (
        <ol aria-label="Instructions Versions">
          {list.map((version) => (
            <VersionItem key={version.id} version={version} current={version.id === currentId} />
          ))}
        </ol>
      )}
      {list.length > 0 && <CompareInstructions organisationId={organisationId} projectId={projectId} versions={list} currentId={currentId} />}
    </div>
  );
}
