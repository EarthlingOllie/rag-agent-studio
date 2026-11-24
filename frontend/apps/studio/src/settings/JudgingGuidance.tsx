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
  useGuidanceDrafting,
  useJudgingGuidance,
  useLatestGuidanceJob,
  useSaveJudgingGuidance,
  useStartGuidanceCheck,
  useStartGuidanceDraft,
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

/** A completed draft an Owner opened in the editor: its job, how many reviews it read, and what it proposes. */
interface OpenedDraft {
  id: string;
  reviewsRead: number;
  proposal: NonNullable<GuidanceJob["draft"]>;
}

/** A completed draft's explanation: each part with how many of the disagreeing reviews it answers. */
function DraftExplanation({ opened }: { opened: OpenedDraft }) {
  return (
    <div role="group" aria-label="The draft's explanation" className="flex flex-col gap-2 rounded-xl bg-sunken px-3.5 py-2.5">
      <p className={text.small}>
        {`Drafted by the Evaluation Model from ${count.format(opened.reviewsRead)} disagreeing reviews outside the held-out half. Edit it, check it on the held-out reviews, then save it.`}
      </p>
      <ul className="flex flex-col gap-1">
        {opened.proposal.explanation.map((part) => (
          <li key={part.part} className={text.body}>
            {part.part}{" "}
            <span className={text.muted}>{`(answers ${count.format(part.reviews.length)} disagreeing ${part.reviews.length === 1 ? "review" : "reviews"})`}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function GuidanceEditor({
  organisationId,
  current,
  opened,
  onDone,
}: {
  organisationId: string;
  current: string;
  /** The completed draft the editor opens on, if any: its text replaces the current one, and saving it saves a `drafted` version. */
  opened: OpenedDraft | null;
  onDone: () => void;
}) {
  const save = useSaveJudgingGuidance(organisationId);
  const start = useStartGuidanceCheck(organisationId);
  const latest = useLatestGuidanceJob(organisationId, true).data;
  // Only a check's result is shown here; a draft is followed in the card.
  const job = latest?.kind === "check" ? latest : null;
  const toast = useToast();
  const [draft, setDraft] = useState(opened ? opened.proposal.text : current);
  const [confirming, setConfirming] = useState(false);
  const editorId = useId();
  const hintId = useId();
  const tooLong = draft.length > GUIDANCE_MAX;
  const checking = latest !== undefined && latest !== null && jobInProgress(latest);
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
      {opened && <DraftExplanation opened={opened} />}
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
          save.mutate({ text: draft, draftId: opened ? opened.id : null }, {
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
          save.mutate({ text: "" }, {
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

/** The latest draft while it runs, or why it ended without one: Owners follow and cancel it. */
function DraftProgress({ organisationId, job }: { organisationId: string; job: GuidanceJob }) {
  const cancel = useCancelGuidanceJob(organisationId);
  if (jobInProgress(job)) {
    return (
      <div className="flex flex-col gap-2">
        <p className={text.small}>
          {job.status === "queued"
            ? "Drafting guidance: waiting to start…"
            : `Drafting guidance from ${count.format(job.reviews_read)} disagreeing reviews…`}
        </p>
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
            Cancel draft
          </button>
        </div>
      </div>
    );
  }
  if (job.status === "failed") return <Notice tone="error">{`The draft failed: ${String(job.error_reason)}`}</Notice>;
  return <p className={text.muted}>The draft was cancelled.</p>;
}

/** A finished draft (only a completed one has a proposal) of the guidance still current (one the Owner hasn't saved over), ready to open; null otherwise. */
function readyDraft(job: GuidanceJob, currentText: string): OpenedDraft | null {
  if (job.draft === null || job.text !== currentText) return null;
  return { id: job.id, reviewsRead: job.reviews_read, proposal: job.draft };
}

/**
 * Drafting guidance from Editors' disagreements (Owners): the Draft button, offered once the current
 * Judging setup has enough reviews (else it says what is missing), its dialog with the estimated Cost,
 * the draft in progress, and a finished draft to open in the editor.
 */
function DraftGuidance({
  organisationId,
  currentText,
  onOpen,
}: {
  organisationId: string;
  currentText: string;
  onOpen: (opened: OpenedDraft) => void;
}) {
  const drafting = useGuidanceDrafting(organisationId);
  const latest = useLatestGuidanceJob(organisationId, true).data;
  const start = useStartGuidanceDraft(organisationId);
  const [confirming, setConfirming] = useState(false);
  const whyId = useId();
  const draft = latest?.kind === "draft" ? latest : null;
  const busy = draft !== null && jobInProgress(draft);
  const ready = draft ? readyDraft(draft, currentText) : null;
  const found = drafting.data;
  const why = drafting.isError ? credentialFailure(drafting.error) : found?.missing;
  return (
    <div role="group" aria-label="Draft guidance" className="flex flex-col gap-2 border-t border-line pt-4">
      <h3 className={text.subheading}>Draft from disagreements</h3>
      {draft && draft.status !== "completed" && <DraftProgress organisationId={organisationId} job={draft} />}
      {ready && (
        <Notice tone="info">
          <span className="flex flex-wrap items-center gap-3">
            {`A draft from ${count.format(ready.reviewsRead)} disagreeing reviews is ready to edit, check and save.`}
            <button
              type="button"
              className={button.secondary}
              onClick={() => {
                onOpen(ready);
              }}
            >
              Open the draft
            </button>
          </span>
        </Notice>
      )}
      <div>
        <button
          type="button"
          className={button.secondary}
          disabled={found?.offered !== true || busy}
          aria-describedby={why ? whyId : undefined}
          onClick={() => {
            start.reset();
            setConfirming(true);
          }}
        >
          Draft guidance
        </button>
      </div>
      {why && (
        <p id={whyId} className={text.muted}>
          {why}
        </p>
      )}
      <p className={text.muted}>
        The Evaluation Model reads the reviews Editors disagreed with, outside the held-out half a check uses, and proposes general rules
        with an explanation. Nothing is saved until you save it.
      </p>
      {found && (
        <ConfirmDialog
          open={confirming}
          title="Draft guidance from disagreements?"
          confirmLabel="Draft guidance"
          busy={start.isPending}
          body={<FormError message={credentialFailure(start.error)} />}
          onCancel={() => {
            setConfirming(false);
          }}
          onConfirm={() => {
            start.mutate(undefined, {
              onSuccess: () => {
                setConfirming(false);
              },
            });
          }}
        >
          {`The Evaluation Model reads about ${count.format(found.reviews_read)} disagreeing reviews and the current guidance. Estimated Cost: ${
            found.estimated_cost_usd === null ? "unknown (the model has no price)" : dollars.format(Number(found.estimated_cost_usd))
          }. It counts in Organisation cost, never against the Evaluation budget.`}
        </ConfirmDialog>
      )}
    </div>
  );
}

/**
 * The Judging guidance card in Organisation settings (Models): the Organisation's own instructions
 * to the Evaluation Model, its current version and every version, each with the check it kept.
 * Every Member reads it; Owners edit, check, save and remove it, and draft it from Editors' disagreements.
 */
export function JudgingGuidanceSection({ organisationId, isOwner }: { organisationId: string; isOwner: boolean }) {
  const guidance = useJudgingGuidance(organisationId);
  const [editing, setEditing] = useState(false);
  const [opened, setOpened] = useState<OpenedDraft | null>(null);
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
                opened={opened}
                onDone={() => {
                  setEditing(false);
                  setOpened(null);
                }}
              />
            ) : (
              <>
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
                <DraftGuidance
                  organisationId={organisationId}
                  currentText={currentText}
                  onOpen={(draft) => {
                    setOpened(draft);
                    setEditing(true);
                  }}
                />
              </>
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
