import { useEffect, useRef, useState } from "react";

import { type Boot, ChatError, type Feedback, giveFeedback, removeFeedback } from "./chat";

/** The API's limit on a comment. */
export const COMMENT_MAX = 1000;

const FAILED = "Your feedback couldn't be saved. Please try again.";

function failure(error: unknown): string {
  // An expired chat says so; anything else is a generic retry.
  return error instanceof ChatError && error.status === 401 ? error.message : FAILED;
}

/**
 * Message Feedback on one of the Agent's replies: a thumbs up ("Helpful") or down ("Not
 * helpful"), with an optional comment once a thumb is chosen. Pressing the chosen thumb again
 * removes the feedback. Each change is saved straight away and shown once the API accepts it.
 */
export function FeedbackControls({
  boot,
  token,
  messageId,
  feedback,
  onChange,
}: {
  boot: Boot;
  token: () => string | null;
  messageId: string;
  feedback: Feedback | null;
  onChange: (feedback: Feedback | null) => void;
}) {
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const box = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (editing) box.current?.focus();
  }, [editing]);

  async function save(change: (token: string) => Promise<Feedback | null>, done: string) {
    const kept = token();
    if (kept === null) {
      setError(FAILED);
      return;
    }
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const saved = await change(kept);
      onChange(saved);
      setNotice(done);
      setEditing(false);
    } catch (problem) {
      setError(failure(problem));
    } finally {
      setSaving(false);
    }
  }

  function thumb(rating: Feedback["rating"]) {
    if (feedback?.rating === rating) {
      void save(async (kept) => {
        await removeFeedback(boot, kept, messageId);
        return null;
      }, "Feedback removed.");
    } else {
      void save((kept) => giveFeedback(boot, kept, messageId, { rating, comment: feedback?.comment ?? null }), "Thanks for your feedback.");
    }
  }

  const button = (rating: Feedback["rating"], label: string, symbol: string) => (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={feedback?.rating === rating}
      disabled={saving}
      onClick={() => {
        thumb(rating);
      }}
    >
      <span aria-hidden="true">{symbol}</span>
    </button>
  );

  return (
    <div className="feedback">
      <div role="group" aria-label="Was this reply helpful?" className="thumbs">
        {button("up", "Helpful", "👍")}
        {button("down", "Not helpful", "👎")}
        {feedback !== null && !editing && (
          <button
            type="button"
            className="comment-toggle"
            disabled={saving}
            onClick={() => {
              setDraft(feedback.comment ?? "");
              setNotice(null);
              setEditing(true);
            }}
          >
            {feedback.comment === null ? "Add a comment" : "Edit comment"}
          </button>
        )}
      </div>
      {feedback?.comment != null && !editing && <p className="comment">“{feedback.comment}”</p>}
      {feedback !== null && editing && (
        <form
          className="comment-form"
          onSubmit={(event) => {
            event.preventDefault();
            const rating = feedback.rating;
            void save((kept) => giveFeedback(boot, kept, messageId, { rating, comment: draft }), "Thanks for your feedback.");
          }}
        >
          <label>
            Comment (optional)
            <textarea
              ref={box}
              value={draft}
              maxLength={COMMENT_MAX}
              rows={2}
              onChange={(event) => {
                setDraft(event.currentTarget.value);
              }}
            />
          </label>
          <span className="comment-actions">
            <button type="submit" disabled={saving}>
              Save comment
            </button>
            <button
              type="button"
              disabled={saving}
              onClick={() => {
                setEditing(false);
              }}
            >
              Cancel
            </button>
          </span>
        </form>
      )}
      {notice && (
        <p role="status" className="feedback-notice">
          {notice}
        </p>
      )}
      {error && (
        <p role="alert" className="feedback-error">
          {error}
        </p>
      )}
    </div>
  );
}
