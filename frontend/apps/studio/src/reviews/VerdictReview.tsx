import type { QueryKey } from "@tanstack/react-query";
import { type SubmitEvent, useId, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { Badge, button, field, text } from "../design";
import { formatTime } from "../settings/AuditPage";
import { REASON_MAX, type ReviewOutcome, type ReviewTarget, reviewFailure, useVerdictReview, type VerdictReview } from "./reviews";

const opposite = (outcome: ReviewOutcome): ReviewOutcome => (outcome === "pass" ? "fail" : "pass");

/** "Agreed by Grace Hopper on 2026-11-06 10:15 UTC, from the Review sample", or Disagreed, with the reviewer's pass or fail. */
function Shown({ review, judged }: { review: VerdictReview; judged: ReviewOutcome }) {
  const agreed = review.outcome === judged;
  const who = review.reviewed_by ?? "a former Member";
  return (
    <div className="flex flex-col gap-1">
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="font-medium">{agreed ? "Agreed" : "Disagreed"}</span>
        <Badge kind={review.outcome === "pass" ? "evaluationPass" : "evaluationFail"} />
        <span className={text.muted}>
          {`by ${who} on ${formatTime(review.reviewed_at)}`}
          {review.from_sample && ", from the Review sample"}
        </span>
      </p>
      {review.purged_at !== null ? (
        <p className={text.muted}>Text purged</p>
      ) : (
        review.reason !== null && <p className="whitespace-pre-wrap text-ink-2">{review.reason}</p>
      )}
    </div>
  );
}

/** The reason field shown on Disagree: optional, up to 1,000 characters. */
function DisagreeForm({
  saving,
  onSave,
  onCancel,
}: {
  saving: boolean;
  onSave: (reason: string) => void;
  onCancel: () => void;
}) {
  const [reason, setReason] = useState("");
  const hintId = useId();
  return (
    <form
      aria-label="Why you disagree"
      className="flex flex-col gap-2"
      onSubmit={(event: SubmitEvent<HTMLFormElement>) => {
        event.preventDefault();
        onSave(reason.trim());
      }}
    >
      <label className={field.label}>
        Why you disagree (optional)
        <textarea
          className={field.textarea}
          rows={2}
          maxLength={REASON_MAX}
          aria-describedby={hintId}
          value={reason}
          onChange={(event) => {
            setReason(event.target.value);
          }}
        />
      </label>
      <p id={hintId} className={field.hint}>
        {`Up to ${String(REASON_MAX)} characters. It helps improve how Verdicts are judged.`}
      </p>
      <div className="flex flex-wrap gap-2">
        <button type="submit" className={button.secondary} disabled={saving}>
          {saving ? "Saving…" : "Save disagreement"}
        </button>
        <button type="button" className={button.ghost} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

/**
 * An Editor's review of a judged Verdict or Live Verdict check where it is shown: Agree or Disagree with the Evaluation Model's
 * pass or fail (a reason field on Disagree), or the existing review with who gave it, when and whether it came from the Review
 * sample, which can be changed or removed. It never changes the Verdict. `reviewable` is false once the text is gone: the review
 * can then only be removed.
 */
export function VerdictReviewControls({
  organisationId,
  target,
  judged,
  review,
  shownKey,
  label,
  reviewable = true,
}: {
  organisationId: string;
  target: ReviewTarget;
  judged: ReviewOutcome;
  review: VerdictReview | null;
  shownKey: QueryKey;
  label: string;
  reviewable?: boolean;
}) {
  const { put, remove } = useVerdictReview(organisationId, target, shownKey);
  const [editing, setEditing] = useState(false);
  const [disagreeing, setDisagreeing] = useState(false);
  const save = (outcome: ReviewOutcome, reason: string | null) => {
    put.mutate(
      { outcome, reason: reason === "" ? null : reason },
      {
        onSuccess: () => {
          setEditing(false);
          setDisagreeing(false);
        },
      },
    );
  };
  const choosing = reviewable && (review === null || editing);
  return (
    <div role="group" aria-label={`Your review of ${label}`} className="flex flex-col gap-2 text-sm">
      <div aria-live="polite">{review !== null && !editing && <Shown review={review} judged={judged} />}</div>
      {choosing && !disagreeing && (
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className={button.secondary}
            disabled={put.isPending}
            onClick={() => {
              save(judged, null);
            }}
          >
            Agree
          </button>
          <button
            type="button"
            className={button.secondary}
            disabled={put.isPending}
            onClick={() => {
              setDisagreeing(true);
            }}
          >
            Disagree
          </button>
          {editing && (
            <button
              type="button"
              className={button.ghost}
              onClick={() => {
                setEditing(false);
              }}
            >
              Cancel
            </button>
          )}
        </div>
      )}
      {choosing && disagreeing && (
        <DisagreeForm
          saving={put.isPending}
          onSave={(reason) => {
            save(opposite(judged), reason);
          }}
          onCancel={() => {
            setDisagreeing(false);
          }}
        />
      )}
      {review !== null && !editing && (
        <div className="flex flex-wrap gap-2">
          {reviewable && (
            <button
              type="button"
              className={button.quiet}
              onClick={() => {
                setEditing(true);
              }}
            >
              Change review
            </button>
          )}
          <button
            type="button"
            className={button.quiet}
            disabled={remove.isPending}
            onClick={() => {
              remove.mutate();
            }}
          >
            Remove review
          </button>
        </div>
      )}
      <FormError message={reviewFailure(put.error ?? remove.error)} />
    </div>
  );
}
