import { type SubmitEvent, useState } from "react";

import { Badge, button, ConfirmDialog, Diff, field, Notice, notice, surface, text } from "../design";
import { formatTime } from "../settings/AuditPage";
import {
  type DraftInstructions,
  type InstructionsReverted,
  type InstructionsVersion,
  useInstructions,
  useInstructionsVersions,
  useIsLatestInstructionsChange,
  usePublishInstructions,
  useRevertInstructions,
  StaleInstructionsError,
  versionFailure,
} from "./instructions";

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

  const failure = latest && !(publish.error instanceof StaleInstructionsError) ? versionFailure(publish.error) : undefined;
  return (
    <form aria-label="Publish Instructions" onSubmit={onSubmit} className="flex flex-col gap-3">
      {failure !== undefined && <Notice tone="error">{failure}</Notice>}
      <div>
        <label htmlFor="publish-instructions-note" className={field.label}>
          Note
        </label>
        <input id="publish-instructions-note" name="note" required maxLength={500} className={field.input} />
        <p className={field.hint}>
          Publishing saves the Draft and freezes it as a new Version, which becomes the Current Version that Agents are published with.
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <button type="submit" disabled={publish.isPending} className={button.primary}>
          {publish.isPending ? "Publishing…" : "Publish Instructions"}
        </button>
        {publish.isSuccess && latest && (
          <span role="status" className={text.muted}>
            Published v{publish.data.number}
          </span>
        )}
      </div>
    </form>
  );
}

/** One Version on the timeline: its chip, the Current badge, the note, who published it and when. */
function VersionItem({ version, current }: { version: InstructionsVersion; current: boolean }) {
  return (
    <li aria-label={`v${String(version.number)}`} className="relative pb-5 pl-7 last:pb-0">
      <span
        aria-hidden="true"
        className={`absolute top-1.5 left-0 size-3 rounded-full border-2 ${current ? "border-accent bg-accent" : "border-field bg-surface"}`}
      />
      <div className="flex flex-wrap items-center gap-2">
        <Badge kind="version" version={version.number} />
        {current && <Badge kind="current" />}
        <span className={text.small}>
          {version.author ? version.author.name : "No author"} · {formatTime(version.created_at)}
        </span>
      </div>
      <p className={`mt-1 ${text.body}`}>{version.note}</p>
      <details className="mt-1">
        <summary className={`cursor-pointer ${text.muted} hover:text-ink`}>Show the Instructions</summary>
        <pre className="mt-2 rounded-xl bg-sunken p-3 font-mono text-[13px] whitespace-pre-wrap text-ink">{version.markdown || "(empty)"}</pre>
      </details>
    </li>
  );
}

/** Compares any two Instructions Versions, or one with the saved Draft, line by line with `Diff`. */
function CompareInstructions({ organisationId, projectId, versions, currentId }: Target & { versions: InstructionsVersion[]; currentId: string | null }) {
  const draft = useInstructions(organisationId, projectId);
  // By default, what publishing the saved Draft would change: from the Current Version, following
  // it when a publish or revert moves it, until the Member picks another side.
  const [picked, setFrom] = useState<string | null>(null);
  const from = picked ?? currentId ?? "draft";
  const [to, setTo] = useState("draft");
  const version = (side: string) => versions.find((each) => each.id === side) as InstructionsVersion;
  const name = (side: string) => (side === "draft" ? "the Draft" : `v${String(version(side).number)}`);
  const picker = (id: string, label: string, value: string, onChange: (side: string) => void) => (
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
        <option value="draft">Draft (saved)</option>
        {versions.map((each) => (
          <option key={each.id} value={each.id}>
            v{each.number}
            {each.id === currentId ? " (Current)" : ""}
          </option>
        ))}
      </select>
    </div>
  );
  let body;
  if (draft.isError) body = <p className={text.muted}>The comparison could not be loaded. Try again shortly.</p>;
  else if (draft.isPending) body = <p className={text.muted}>Comparing…</p>;
  else {
    const markdown = (side: string) => (side === "draft" ? draft.data.markdown : version(side).markdown);
    const before = markdown(from);
    const after = markdown(to);
    body =
      before === after ? (
        <p className={text.muted}>
          No differences: {name(from)} and {name(to)} are the same.
        </p>
      ) : (
        <Diff label={`Changes from ${name(from)} to ${name(to)}`} before={before} after={after} />
      );
  }
  return (
    <section aria-labelledby="compare-instructions-heading" className={`flex flex-col gap-3 ${surface.panel}`}>
      <h4 id="compare-instructions-heading" className={text.subheading}>
        Compare
      </h4>
      <div className="grid gap-3 sm:grid-cols-2">
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

  const failure = latest ? versionFailure(revert.error) : undefined;
  let revertControl = null;
  if (previous && !archived) {
    const label = `v${String(previous.number)}`;
    revertControl = (
      <>
        <button
          type="button"
          onClick={() => {
            revert.reset();
            setConfirming(true);
          }}
          className={button.secondary}
        >
          Revert to {label}
        </button>
        <ConfirmDialog
          open={confirming}
          destructive
          title={`Revert to ${label}?`}
          confirmLabel={`Yes, revert to ${label}`}
          busy={revert.isPending}
          onCancel={() => {
            setConfirming(false);
          }}
          onConfirm={() => {
            revert.mutate(undefined, {
              onSuccess: onReverted,
              onSettled: () => {
                setConfirming(false);
              },
            });
          }}
        >
          Revert the Current Version to {label}? Agents published from now on use {label}. The Draft isn&apos;t changed.
        </ConfirmDialog>
      </>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className={text.body}>
          {current
            ? `Current Version: v${String(current.number)}.`
            : "Not published yet. Publish the Draft to make v1, the Current Version."}
        </p>
        {revertControl}
      </div>
      {failure !== undefined && <Notice tone="error">{failure}</Notice>}
      {revert.isSuccess && latest && (
        <p role="status" className={notice.success}>
          Reverted to v{revert.data.number}
        </p>
      )}
      {list.length > 0 && (
        <ol aria-label="Instructions Versions" className="relative before:absolute before:top-2 before:bottom-2 before:left-[5px] before:w-0.5 before:bg-line">
          {list.map((version) => (
            <VersionItem key={version.id} version={version} current={version.id === currentId} />
          ))}
        </ol>
      )}
      {list.length > 0 && <CompareInstructions organisationId={organisationId} projectId={projectId} versions={list} currentId={currentId} />}
    </div>
  );
}
