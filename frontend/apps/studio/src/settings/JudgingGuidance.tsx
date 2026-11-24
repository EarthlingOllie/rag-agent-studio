import { type SubmitEvent, useId, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { Badge, button, ConfirmDialog, field, Meter, Notice, Skeleton, surface, text, useToast } from "../design";
import { credentialFailure } from "./credentials";
import {
  GUIDANCE_MAX,
  type GuidanceCheck,
  type GuidanceJob,
  type GuidanceVersion,
  jobInProgress,
  useCancelGuidanceJob,
  useJudgingGuidance,
  useLatestGuidanceJob,
  useSaveJudgingGuidance,
  useStartGuidanceCheck,
} from "./judgingGuidance";

const savedDay = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
const count = new Intl.NumberFormat("en-GB");

function saved(version: GuidanceVersion): string {
  return `saved by ${version.saved_by ?? "a deleted Member"} on ${savedDay.format(new Date(version.saved_at))}`;
}

function GuidanceText({ version }: { version: GuidanceVersion }) {
  if (version.text === "") return <p className={text.muted}>No guidance (removed)</p>;
  return <blockquote className="whitespace-pre-wrap border-l-2 border-field pl-3 text-sm text-ink">{version.text}</blockquote>;
}

const dollars = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 4 });

/** "would agree on x of y (now z)": a check's agreement on the held-out reviews beside the current Judging setup's. */
function wouldAgree({ agreed, of, before }: { agreed: number; of: number; before: number }): string {
  return `would agree on ${count.format(agreed)} of ${count.format(of)} (now ${count.format(before)})`;
}

function disagreements({ false_passes, false_fails }: { false_passes: number; false_fails: number }): string {
  return `false passes: ${count.format(false_passes)}, false fails: ${count.format(false_fails)}`;
}

/** The check a saved version keeps: its result on the held-out reviews before it was saved. */
function SavedCheck({ check }: { check: GuidanceCheck }) {
  return (
    <p className={`${text.small} flex flex-wrap items-center gap-2`}>
      {`Checked before saving: ${wouldAgree({ agreed: check.agreed, of: check.reviews, before: check.agreed_before })}, ${disagreements(check)}.`}
      {check.low_sample && <Badge kind="lowSample" />}
    </p>
  );
}

/** Whether a completed check of this text shows lower agreement than the current Judging setup's. */
function agreementDrops(job: GuidanceJob | null | undefined, draft: string): job is GuidanceJob {
  return job?.status === "completed" && job.text === draft.trim() && job.agreed < job.agreed_before;
}

/** The latest check: its progress while it runs, then its result, marked out of date once the text changes. */
function CheckResult({ organisationId, job, draft }: { organisationId: string; job: GuidanceJob; draft: string }) {
  const cancel = useCancelGuidanceJob(organisationId);
  if (jobInProgress(job)) {
    return (
      <div className="flex flex-col gap-2">
        <p className={text.small}>{`Checking on ${count.format(job.held_out)} held-out reviews…`}</p>
        <Meter label="Check progress" value={job.judged + job.left_out} max={job.held_out} unit="reviews" progress />
        <FormError message={credentialFailure(cancel.error)} />
        <div>
          <button
            type="button"
            className={button.secondary}
            disabled={cancel.isPending}
            onClick={() => {
              cancel.mutate(job.id);
            }}
          >
            Cancel check
          </button>
        </div>
      </div>
    );
  }
  if (job.status === "failed") return <Notice tone="error">{`The check failed: ${String(job.error_reason)}`}</Notice>;
  if (job.status === "cancelled") return <p className={text.muted}>The check was cancelled.</p>;
  const outOfDate = job.text !== draft.trim();
  return (
    <div className="flex flex-col gap-2">
      <p className={`${text.body} flex flex-wrap items-center gap-2`}>
        <span className="font-medium">{`On held-out reviews, this guidance ${wouldAgree({ agreed: job.agreed, of: job.judged, before: job.agreed_before })}.`}</span>
        {job.low_sample && <Badge kind="lowSample" />}
      </p>
      <p className={text.small}>
        {`${disagreements(job).replace(/^f/, "F")}.`}
        {job.left_out > 0 && ` ${count.format(job.left_out)} left out: their replies were deleted.`}
        {` Cost ${dollars.format(Number(job.cost_usd))}.`}
      </p>
      {outOfDate && <Notice tone="warning">Out of date: the text has changed since this check. Check again before saving.</Notice>}
    </div>
  );
}

function GuidanceEditor({ organisationId, current, onDone }: { organisationId: string; current: string; onDone: () => void }) {
  const save = useSaveJudgingGuidance(organisationId);
  const start = useStartGuidanceCheck(organisationId);
  const job = useLatestGuidanceJob(organisationId, true).data;
  const toast = useToast();
  const [draft, setDraft] = useState(current);
  const [confirming, setConfirming] = useState(false);
  const editorId = useId();
  const hintId = useId();
  const tooLong = draft.length > GUIDANCE_MAX;
  const checking = job !== undefined && job !== null && jobInProgress(job);
  const checked = job?.status === "completed" && job.text === draft.trim();
  return (
    <form
      aria-label="Edit the Judging guidance"
      className="flex flex-col gap-3"
      onSubmit={(event: SubmitEvent<HTMLFormElement>) => {
        event.preventDefault();
        setConfirming(true);
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
            start.reset();
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
      <div aria-live="polite" aria-label="Check result" role="group" className="flex flex-col gap-2">
        {job && <CheckResult organisationId={organisationId} job={job} draft={draft} />}
      </div>
      <FormError message={credentialFailure(start.error)} />
      <div className="flex flex-wrap items-center gap-3">
        <button type="submit" className={button.primary} disabled={save.isPending || tooLong}>
          {save.isPending ? "Saving…" : "Save guidance"}
        </button>
        <button
          type="button"
          className={button.secondary}
          disabled={tooLong || checking || start.isPending}
          onClick={() => {
            start.mutate(draft);
          }}
        >
          {checked ? "Check again" : "Check guidance"}
        </button>
        <button type="button" className={button.secondary} disabled={save.isPending} onClick={onDone}>
          Cancel
        </button>
      </div>
      <p className={text.muted}>
        A check re-judges the held-out half of the Review sample reviews with this text, without saving it or changing any Verdict. Its
        Cost counts in Organisation cost, never against the Evaluation budget.
      </p>
      <ConfirmDialog
        open={confirming}
        title="Save the Judging guidance?"
        confirmLabel="Save guidance"
        busy={save.isPending}
        body={
          <>
            {agreementDrops(job, draft) && (
              <Notice tone="warning">
                {`The latest check shows lower agreement: on held-out reviews this guidance ${wouldAgree({ agreed: job.agreed, of: job.judged, before: job.agreed_before })}. You can still save it.`}
              </Notice>
            )}
            <FormError message={credentialFailure(save.error)} />
          </>
        }
        onCancel={() => {
          save.reset();
          setConfirming(false);
        }}
        onConfirm={() => {
          save.mutate(draft, {
            onSuccess: (next) => {
              const version = next.current;
              toast.show(
                version === null || version.text === ""
                  ? "Judging guidance is removed: new judgements use the Evaluation Model's own instructions."
                  : `Judging guidance version ${String(version.version)} is saved: new judgements use it.`,
              );
              setConfirming(false);
              onDone();
            },
          });
        }}
      >
        {checked
          ? "New Evaluation Runs and Live Verdicts are judged with it, and it starts a new Judging setup."
          : "New Evaluation Runs and Live Verdicts are judged with it, and it starts a new Judging setup. This text hasn't been checked on held-out reviews."}
      </ConfirmDialog>
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
 * to the Evaluation Model, its current version and every version, each with the check it kept.
 * Every Member reads it; Owners edit, check, save and remove it.
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
              {current.check && <SavedCheck check={current.check} />}
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
                    {version.check && <SavedCheck check={version.check} />}
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
