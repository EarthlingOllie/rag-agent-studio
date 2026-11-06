import { type SubmitEvent, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { formatTime } from "../settings/AuditPage";
import {
  type InstructionsReverted,
  type InstructionsVersion,
  useInstructionsVersions,
  useIsLatestInstructionsChange,
  usePublishInstructions,
  useRevertInstructions,
  versionFailure,
} from "./instructions";
import { BUTTON, INPUT } from "./ProjectsPage";

type Target = { organisationId: string; projectId: string };

/** Publishes the Draft as written in the editor (`markdown()`), with a note, as the next Version. */
export function PublishInstructionsForm({
  organisationId,
  projectId,
  markdown,
  onPublished,
}: Target & { markdown: () => string; onPublished: (version: InstructionsVersion) => void }) {
  const publish = usePublishInstructions(organisationId, projectId);
  const latest = useIsLatestInstructionsChange(organisationId, projectId, publish.submittedAt);

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const note = new FormData(form).get("note") as string;
    publish.mutate(
      { markdown: markdown(), note },
      {
        onSuccess: (version) => {
          form.reset();
          onPublished(version);
        },
      },
    );
  }

  return (
    <form aria-label="Publish Instructions" onSubmit={onSubmit} className="space-y-2 rounded border border-slate-300 p-3">
      <FormError message={latest ? versionFailure(publish.error) : undefined} />
      <label className="block">
        Note
        <input name="note" required maxLength={500} className={INPUT} />
      </label>
      <p className="text-sm text-slate-700">
        Publishing saves the Draft and freezes it as a new Version, which becomes the Current Version that Agents are published with.
      </p>
      <div className="flex items-center gap-3">
        <button type="submit" disabled={publish.isPending} className={BUTTON}>
          {publish.isPending ? "Publishing…" : "Publish Instructions"}
        </button>
        {publish.isSuccess && latest && (
          <span role="status" className="text-sm text-slate-700">
            Published v{publish.data.number}
          </span>
        )}
      </div>
    </form>
  );
}

function VersionItem({ version, current }: { version: InstructionsVersion; current: boolean }) {
  return (
    <li aria-label={`v${String(version.number)}`} className="space-y-1 border-t border-slate-200 py-2">
      <div className="flex items-center gap-2">
        <span className="font-semibold">v{version.number}</span>
        {current && <span className="rounded bg-emerald-100 px-2 text-sm text-emerald-900">Current</span>}
      </div>
      <p>{version.note}</p>
      <p className="text-sm text-slate-700">
        {version.author ? version.author.name : "No author"} · {formatTime(version.created_at)}
      </p>
      <details>
        <summary className="cursor-pointer text-sm underline">Show the Instructions</summary>
        <pre className="mt-1 whitespace-pre-wrap rounded bg-slate-50 p-2 text-sm">{version.markdown || "(empty)"}</pre>
      </details>
    </li>
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
          className="rounded bg-red-700 px-2 py-1 text-white"
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
        <p role="status" className="text-sm text-slate-700">
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
    </div>
  );
}
