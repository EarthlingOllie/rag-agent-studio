import { type SubmitEvent, useId, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { button, ConfirmDialog, field, Skeleton, surface, text, useToast } from "../design";
import { credentialFailure } from "./credentials";
import { GUIDANCE_MAX, type GuidanceVersion, useJudgingGuidance, useSaveJudgingGuidance } from "./judgingGuidance";

const savedDay = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
const count = new Intl.NumberFormat("en-GB");

function saved(version: GuidanceVersion): string {
  return `saved by ${version.saved_by ?? "a deleted Member"} on ${savedDay.format(new Date(version.saved_at))}`;
}

function GuidanceText({ version }: { version: GuidanceVersion }) {
  if (version.text === "") return <p className={text.muted}>No guidance (removed)</p>;
  return <blockquote className="whitespace-pre-wrap border-l-2 border-field pl-3 text-sm text-ink">{version.text}</blockquote>;
}

function GuidanceEditor({ organisationId, current, onDone }: { organisationId: string; current: string; onDone: () => void }) {
  const save = useSaveJudgingGuidance(organisationId);
  const toast = useToast();
  const [draft, setDraft] = useState(current);
  const editorId = useId();
  const hintId = useId();
  const tooLong = draft.length > GUIDANCE_MAX;
  return (
    <form
      aria-label="Edit the Judging guidance"
      className="flex flex-col gap-3"
      onSubmit={(event: SubmitEvent<HTMLFormElement>) => {
        event.preventDefault();
        save.mutate(draft, {
          onSuccess: (next) => {
            const version = next.current;
            toast.show(
              version === null || version.text === ""
                ? "Judging guidance is removed: new judgements use the Evaluation Model's own instructions."
                : `Judging guidance version ${String(version.version)} is saved: new judgements use it.`,
            );
            onDone();
          },
        });
      }}
    >
      <div className="flex flex-col">
        <label htmlFor={editorId} className={field.label}>
          Judging guidance
        </label>
        <textarea
          id={editorId}
          // The editor opens on demand, so focus moves into it.
          autoFocus
          rows={6}
          aria-describedby={hintId}
          aria-invalid={tooLong}
          className={field.textarea}
          value={draft}
          onChange={(event) => {
            save.reset();
            setDraft(event.target.value);
          }}
        />
        <p id={hintId} className={tooLong ? field.error : field.hint}>
          {`${count.format(draft.length)} of ${count.format(GUIDANCE_MAX)} characters. `}
          Every save starts a new Judging setup: new Evaluation Runs and Live Verdicts are judged with it, and earlier ones keep theirs.
          Evaluation Model agreement starts again under it, and the Live score drop alert stays quiet for the previous Live Version
          until that Version has 30 Live Verdicts under it.
        </p>
      </div>
      <FormError message={credentialFailure(save.error)} />
      <div className="flex flex-wrap items-center gap-3">
        <button type="submit" className={button.primary} disabled={save.isPending || tooLong}>
          {save.isPending ? "Saving…" : "Save guidance"}
        </button>
        <button type="button" className={button.secondary} disabled={save.isPending} onClick={onDone}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function RemoveGuidance({ organisationId }: { organisationId: string }) {
  const save = useSaveJudgingGuidance(organisationId);
  const toast = useToast();
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        className={button.danger}
        onClick={() => {
          setOpen(true);
        }}
      >
        Remove guidance
      </button>
      <ConfirmDialog
        open={open}
        title="Remove the Judging guidance?"
        confirmLabel="Remove guidance"
        destructive
        busy={save.isPending}
        body={<FormError message={credentialFailure(save.error)} />}
        onCancel={() => {
          save.reset();
          setOpen(false);
        }}
        onConfirm={() => {
          save.mutate("", {
            onSuccess: () => {
              setOpen(false);
              toast.show("Judging guidance is removed: new judgements use the Evaluation Model's own instructions.");
            },
          });
        }}
      >
        New Evaluation Runs and Live Verdicts are judged by the Evaluation Model's own instructions. This saves an empty version, so
        earlier versions stay in the history. It starts a new Judging setup: Evaluation Model agreement starts again, and the Live
        score drop alert stays quiet for the previous Live Version until that Version has 30 Live Verdicts under it.
      </ConfirmDialog>
    </>
  );
}

/**
 * The Judging guidance card in Organisation settings (Models): the Organisation's own instructions
 * to the Evaluation Model, its current version and every version. Every Member reads it; Owners
 * edit and remove it.
 */
export function JudgingGuidanceSection({ organisationId, isOwner }: { organisationId: string; isOwner: boolean }) {
  const guidance = useJudgingGuidance(organisationId);
  const [editing, setEditing] = useState(false);
  const current = guidance.data?.current ?? null;
  const currentText = current?.text ?? "";
  return (
    <section aria-labelledby="judging-guidance-heading" className={`${surface.panel} flex max-w-2xl flex-col gap-4`}>
      <div className="flex flex-col gap-1">
        <h2 id="judging-guidance-heading" className={text.heading}>
          Judging guidance
        </h2>
        <p className={text.muted}>
          Your Organisation's own rules for the Evaluation Model, added to every judgement of Evaluation Runs and Live Verdicts, up to
          2,000 characters. Change it rarely: each save starts a new Judging setup.
        </p>
      </div>
      {guidance.isError && <p role="alert" className={text.muted}>The Judging guidance could not be loaded. Try again shortly.</p>}
      {guidance.isPending && <Skeleton label="Loading the Judging guidance" />}
      {guidance.data && (
        <>
          {current === null || currentText === "" ? (
            <p className={text.muted}>No guidance: the Evaluation Model judges by its own instructions alone.</p>
          ) : (
            <div role="group" aria-label="Current guidance" className="flex flex-col gap-2">
              <p className={text.small}>{`Version ${String(current.version)}, ${saved(current)}`}</p>
              <GuidanceText version={current} />
            </div>
          )}
          {isOwner ? (
            editing ? (
              <GuidanceEditor
                organisationId={organisationId}
                current={currentText}
                onDone={() => {
                  setEditing(false);
                }}
              />
            ) : (
              <div className="flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  className={button.secondary}
                  onClick={() => {
                    setEditing(true);
                  }}
                >
                  Edit guidance
                </button>
                {currentText !== "" && <RemoveGuidance organisationId={organisationId} />}
              </div>
            )
          ) : (
            <p className={text.muted}>Only Owners can change the Judging guidance.</p>
          )}
          {guidance.data.versions.length > 0 && (
            <div className="flex flex-col gap-2 border-t border-line pt-4">
              <h3 className={text.subheading}>Version history</h3>
              <ol aria-label="Guidance versions" className="flex flex-col gap-3">
                {guidance.data.versions.map((version) => (
                  <li key={version.version} className="flex flex-col gap-1">
                    <p className={text.small}>{`Version ${String(version.version)}, ${version.source}, ${saved(version)}`}</p>
                    <GuidanceText version={version} />
                  </li>
                ))}
              </ol>
            </div>
          )}
        </>
      )}
    </section>
  );
}
