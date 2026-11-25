import { button } from "../design";
import type { Agent } from "./agents";

/**
 * Someone else saved the Draft after the revision a write was made on: the Editor loads their
 * Draft (losing the write) or saves theirs over it. `latest` is the Agent carried by the
 * `StaleDraftError` the write was refused with; both callbacks are handed it back. Shared by every
 * flow that writes to the Draft.
 */
export function DraftConflict({
  latest,
  onLoad,
  onOverwrite,
}: {
  latest: Agent;
  onLoad: (latest: Agent) => void;
  onOverwrite: (latest: Agent) => void;
}) {
  return (
    <div role="alert" className="mx-6 my-4 space-y-2 rounded-xl bg-flag-soft p-3 text-sm text-flag">
      <p>
        Someone else saved this Draft while you were editing (saved {new Date(latest.draft_updated_at).toLocaleString()}). Your
        changes aren&apos;t saved. Load their Draft, or save yours over it.
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className={button.secondary}
          onClick={() => {
            onLoad(latest);
          }}
        >
          Load their changes
        </button>
        <button
          type="button"
          className={button.secondary}
          onClick={() => {
            onOverwrite(latest);
          }}
        >
          Save mine over theirs
        </button>
      </div>
    </div>
  );
}
