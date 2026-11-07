import { useEffect, useId, useRef, useState } from "react";

import { type Boot, ChatError, dismissRatingPrompt, type Rating, rateConversation } from "./chat";

const SCORES = [1, 2, 3, 4, 5] as const;
const QUESTION = "How would you rate this chat?";
const FAILED = "Your rating couldn't be saved. Please try again.";

/** No rating yet and the rating prompt not dismissed. */
export const UNRATED: Rating = { score: null, prompt_dismissed: false };

/**
 * Whether the rating prompt shows during the chat: after the Live Version's Nth reply (never
 * when N is 0, which asks only at the end), until the Visitor rates or dismisses it.
 */
export function promptDue(boot: Boot, rating: Rating, replies: number): boolean {
  const after = boot.rating_prompt_after;
  return rating.score === null && !rating.prompt_dismissed && after > 0 && replies >= after;
}

/**
 * The Conversation Rating in the widget's footer.
 *
 * - During the chat (`ending` false): the 1–5 prompt once it is due (see `promptDue`), with "Not
 *   now" to dismiss it for this Conversation; once rated, the rating with "Change rating".
 * - On "End chat" without a rating (`ending` true): the prompt with "End without rating" and
 *   "Keep chatting"; rating or skipping ends the chat (`onEnd`).
 *
 * Each rating is saved straight away and shown once the API accepts it; a dismissal is saved
 * too, but the prompt hides either way.
 */
export function RatingPrompt({
  boot,
  token,
  rating,
  replies,
  ending,
  onChange,
  onEnd,
  onKeepChatting,
}: {
  boot: Boot;
  token: () => string | null;
  rating: Rating;
  replies: number;
  ending: boolean;
  onChange: (rating: Rating) => void;
  onEnd: () => void;
  onKeepChatting: () => void;
}) {
  const [changing, setChanging] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const group = useRef<HTMLDivElement | null>(null);
  const questionId = useId();

  // "End chat" removes the chat's controls, so focus moves to the prompt; so does "Change rating".
  useEffect(() => {
    if (ending || changing) group.current?.querySelector("button")?.focus();
  }, [ending, changing]);

  async function rate(score: number) {
    const kept = token();
    if (kept === null) {
      setError(FAILED);
      return;
    }
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      onChange(await rateConversation(boot, kept, score));
      setChanging(false);
      setNotice("Thanks for rating this chat.");
      if (ending) onEnd();
    } catch (problem) {
      // An expired chat can't be rated any more, so ending it goes ahead.
      if (ending && problem instanceof ChatError && problem.status === 401) onEnd();
      else setError(problem instanceof ChatError && problem.status === 401 ? problem.message : FAILED);
    } finally {
      setSaving(false);
    }
  }

  async function dismiss() {
    const kept = token();
    onChange({ ...rating, prompt_dismissed: true });
    if (kept !== null) await dismissRatingPrompt(boot, kept);
  }

  const status = (
    <>
      {notice && (
        <p role="status" className="rating-notice">
          {notice}
        </p>
      )}
      {error && (
        <p role="alert" className="rating-error">
          {error}
        </p>
      )}
    </>
  );

  if (!ending && !changing) {
    if (rating.score !== null) {
      return (
        <div className="rating rated">
          <p>
            You rated this chat {rating.score} out of 5.{" "}
            <button
              type="button"
              onClick={() => {
                setNotice(null);
                setChanging(true);
              }}
            >
              Change rating
            </button>
          </p>
          {status}
        </div>
      );
    }
    if (!promptDue(boot, rating, replies)) return null;
  }

  return (
    <div className="rating">
      <p id={questionId}>{ending ? `Before you go: ${boot.ui_text.rate_conversation ?? QUESTION}` : (boot.ui_text.rate_conversation ?? QUESTION)}</p>
      <div ref={group} role="group" aria-labelledby={questionId} className="scores">
        {SCORES.map((score) => (
          <button
            key={score}
            type="button"
            aria-label={`${String(score)} out of 5`}
            aria-pressed={rating.score === score}
            disabled={saving}
            onClick={() => {
              void rate(score);
            }}
          >
            {score}
            <span aria-hidden="true"> ★</span>
          </button>
        ))}
      </div>
      <p className="rating-actions">
        {ending ? (
          <>
            <button
              type="button"
              disabled={saving}
              onClick={() => {
                // Saved before the chat ends, while its token is still accepted.
                void dismiss().then(onEnd);
              }}
            >
              End without rating
            </button>
            <button type="button" disabled={saving} onClick={onKeepChatting}>
              Keep chatting
            </button>
          </>
        ) : (
          <button
            type="button"
            disabled={saving}
            onClick={() => {
              if (changing) setChanging(false);
              else void dismiss();
            }}
          >
            {changing ? "Cancel" : "Not now"}
          </button>
        )}
      </p>
      {status}
    </div>
  );
}
