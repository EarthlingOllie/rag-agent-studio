import { Link } from "@tanstack/react-router";
import { type SubmitEvent, useId, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { Badge, button, EmptyState, field, layout, Notice, PageHeader, Skeleton, surface, Tag, text, ToastProvider, useToast } from "../design";
import { useOrganisationRole } from "../projects/ProjectsPage";
import { credentialFailure } from "../settings/credentials";
import {
  REASON_MAX,
  type ReviewOutcome,
  type ReviewSampleItem,
  type SampleReview,
  targetOf,
  useReviewSampleItem,
  useSkipSampleItem,
  useSubmitSampleReview,
} from "./reviews";

/** What is being checked, of a Run Verdict's answer or a Live Verdict's reply. */
const CHECKS: Record<ReviewSampleItem["check"], (judged: string) => string> = {
  reference_answer: (judged) => `Does the ${judged} agree in meaning with the Reference answer?`,
  grounding: (judged) => `Is every claim in the ${judged} supported by the excerpts it cited?`,
  answers_question: (judged) => `Does the ${judged} answer the question it was asked?`,
};

const isLive = (item: ReviewSampleItem) => item.live_verdict_id !== null;

function OutcomeBadge({ outcome }: { outcome: ReviewOutcome }) {
  return <Badge kind={outcome === "pass" ? "evaluationPass" : "evaluationFail"} />;
}

/** A labelled block of the item: what the Evaluation Model was given. */
function Given({ label, children }: { label: string; children: string }) {
  return (
    <div className="flex flex-col gap-1">
      <h3 className={text.small}>{label}</h3>
      <p className="whitespace-pre-wrap text-sm text-ink">{children}</p>
    </div>
  );
}

/** A Live reply's Remembered turns, oldest first, as the Evaluation Model was given them. */
function RememberedTurns({ turns }: { turns: ReviewSampleItem["remembered_turns"] }) {
  const headingId = useId();
  if (turns.length === 0) return null;
  return (
    <div className="flex flex-col gap-2">
      <h3 id={headingId} className={text.small}>
        Earlier in the Conversation
      </h3>
      <ul aria-labelledby={headingId} className="flex flex-col gap-2">
        {turns.map((turn, index) => (
          <li key={index} className="flex flex-col gap-1 rounded-xl bg-sunken px-3.5 py-2.5 text-sm text-ink">
            <p className="whitespace-pre-wrap">
              <span className="text-muted">Visitor: </span>
              {turn.question}
            </p>
            <p className="whitespace-pre-wrap">
              <span className="text-muted">Reply: </span>
              {turn.answer}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The judged Verdict or Live Verdict check as the Evaluation Model saw it: never its outcome or reason. */
function Item({ item }: { item: ReviewSampleItem }) {
  const live = isLive(item);
  const excerptsId = useId();
  return (
    <article aria-label="Item to review" className={`${surface.panel} flex flex-col gap-4`}>
      <div className="flex flex-col gap-1">
        <p className={text.small}>{`${item.agent_name} · ${live ? "Live reply" : "Evaluation Run"}`}</p>
        <h2 className={text.subheading}>{CHECKS[item.check](live ? "reply" : "answer")}</h2>
      </div>
      <RememberedTurns turns={item.remembered_turns} />
      <Given label="Question">{item.question}</Given>
      {item.reference_answer !== null && <Given label="Reference answer">{item.reference_answer}</Given>}
      <Given label={live ? "Reply" : "Answer"}>{item.answer}</Given>
      <div className="flex flex-col gap-2">
        <h3 id={excerptsId} className={text.small}>
          Excerpts it was given
        </h3>
        {item.chunks.length === 0 ? (
          <p className={text.muted}>{live ? "None: it was given no excerpts." : "None: the answer cited nothing."}</p>
        ) : (
          <ul aria-labelledby={excerptsId} className="flex flex-col gap-2">
            {item.chunks.map((chunk) => (
              <li key={chunk.label} className="flex flex-col gap-1 rounded-xl bg-sunken px-3.5 py-2.5">
                <span className="flex flex-wrap items-center gap-2 text-xs text-muted">
                  <span className="font-mono">{chunk.label}</span>
                  <span>{chunk.document_name}</span>
                  {chunk.cited && <Tag>Cited</Tag>}
                </span>
                <span className="text-sm text-ink">{chunk.text}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </article>
  );
}

/** Once reviewed: the Evaluation Model's pass or fail and reason, and a reason field when the Editor differed. */
function Reveal({
  organisationId,
  item,
  review,
  onNext,
}: {
  organisationId: string;
  item: ReviewSampleItem;
  review: SampleReview;
  onNext: () => void;
}) {
  const save = useSubmitSampleReview(organisationId);
  const toast = useToast();
  const [reason, setReason] = useState("");
  const hintId = useId();
  return (
    <section aria-labelledby="reveal-heading" className={`${surface.panel} flex flex-col gap-4`}>
      <h2 id="reveal-heading" className={text.subheading}>
        {review.agreed ? "You agreed with the Evaluation Model" : "You differed from the Evaluation Model"}
      </h2>
      <dl className="grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2 text-sm">
        <dt className="text-muted">You</dt>
        <dd>
          <OutcomeBadge outcome={review.outcome} />
        </dd>
        <dt className="text-muted">Evaluation Model</dt>
        <dd className="flex flex-wrap items-center gap-2">
          <OutcomeBadge outcome={review.evaluation_model_outcome} />
          <span className="text-ink">{review.evaluation_model_reason}</span>
        </dd>
      </dl>
      {!review.agreed && (
        <form
          aria-label="Why you differ"
          className="flex flex-col gap-2"
          onSubmit={(event: SubmitEvent<HTMLFormElement>) => {
            event.preventDefault();
            save.mutate(
              { ...targetOf(item), outcome: review.outcome, reason: reason.trim() },
              {
                onSuccess: () => {
                  toast.show("Your reason is saved.");
                },
              },
            );
          }}
        >
          <label className={field.label}>
            Why you differ (optional)
            <textarea
              className={field.textarea}
              rows={3}
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
          <FormError message={credentialFailure(save.error)} />
          <button type="submit" className={`${button.secondary} self-start`} disabled={save.isPending || reason.trim() === ""}>
            {save.isPending ? "Saving…" : "Save reason"}
          </button>
        </form>
      )}
      <button type="button" className={`${button.primary} self-start`} onClick={onNext}>
        Next
      </button>
    </section>
  );
}

/** The Editor's pass or fail, given before the Evaluation Model's is shown, or Skip. */
function Decide({
  organisationId,
  item,
  onReviewed,
  onSkip,
}: {
  organisationId: string;
  item: ReviewSampleItem;
  onReviewed: (review: SampleReview) => void;
  onSkip: () => void;
}) {
  const submit = useSubmitSampleReview(organisationId);
  const skip = useSkipSampleItem(organisationId);
  const decide = (outcome: ReviewOutcome) => {
    submit.mutate({ ...targetOf(item), outcome }, { onSuccess: onReviewed });
  };
  // Pass and Fail look alike, so neither is suggested.
  return (
    <div className="flex flex-col gap-3">
      <FormError message={credentialFailure(submit.error)} />
      <div role="group" aria-label="Your verdict" className="flex flex-wrap gap-3">
        <button type="button" className={button.secondary} disabled={submit.isPending} onClick={() => { decide("pass"); }}>
          Pass
        </button>
        <button type="button" className={button.secondary} disabled={submit.isPending} onClick={() => { decide("fail"); }}>
          Fail
        </button>
        <button type="button" className={button.ghost} disabled={submit.isPending || skip.isPending}
          onClick={() => {
            // Counted for the agreement card; the next item is drawn whether or not the count was kept.
            skip.mutate(undefined, { onSettled: onSkip });
          }}
        >
          Skip
        </button>
      </div>
      <p className={text.muted}>The Evaluation Model's pass or fail and reason are shown once you've given yours.</p>
    </div>
  );
}

function Sample({ organisationId }: { organisationId: string }) {
  const next = useReviewSampleItem(organisationId);
  const [review, setReview] = useState<SampleReview | null>(null);
  const draw = () => {
    setReview(null);
    void next.refetch();
  };
  if (next.isError) {
    return <EmptyState tone="error" title="The Review sample could not be loaded" description="Try again shortly." />;
  }
  if (next.isPending || next.isFetching) return <Skeleton label="Loading the next item" lines={5} />;
  const { item, reviewed, reviewed_by_you: byYou } = next.data;
  return (
    <div className="flex flex-col gap-5">
      <Notice tone="info">{`${String(reviewed)} sample reviews so far, ${String(byYou)} of them yours.`}</Notice>
      {item === null ? (
        <EmptyState
          icon="check"
          title="Nothing to review"
          description="Every judged Verdict and Live Verdict check under the current Judging setup has been reviewed. New ones come with each Evaluation Run and judged Live reply."
          action={
            <Link to="/organisations/$organisationId/settings/models" params={{ organisationId }} className={text.link}>
              Back to Models settings
            </Link>
          }
        />
      ) : (
        <>
          <Item item={item} />
          {review === null ? (
            <Decide organisationId={organisationId} item={item} onReviewed={setReview} onSkip={draw} />
          ) : (
            <Reveal organisationId={organisationId} item={item} review={review} onNext={draw} />
          )}
        </>
      )}
    </div>
  );
}

/**
 * The Review sample: one judged Verdict or Live Verdict check at a time, drawn at random from those judged under the current Judging setup
 * not yet reviewed. The Editor gives their own pass or fail before the Evaluation Model's is revealed, so
 * Evaluation Model agreement isn't skewed towards the Verdicts people already doubted.
 */
export function ReviewSamplePage() {
  const { organisationId } = useOrganisationRole();
  return (
    <ToastProvider>
      <div className={`${layout.stack} max-w-3xl`}>
        <PageHeader
        title="Review sample"
        description="Judge each answer yourself, then see what the Evaluation Model said. Reviews never change a Verdict or a score; they measure how often the Evaluation Model is right."
      />
        <Sample organisationId={organisationId} />
      </div>
    </ToastProvider>
  );
}
