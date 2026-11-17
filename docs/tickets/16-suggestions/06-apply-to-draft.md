# 06: Applying a Suggestion to the Draft

**Ticket:** `16-06` · **Spec:** [Suggestions](../../specs/16-suggestions-spec.md)

**What to build:** An Editor reviews a Suggestion as a Diff against the current Draft and applies it whole; unrelated Draft edits merge cleanly, clashes are listed for the Editor to resolve, and nothing is Published.

**Blocked by:**
- [16-01: Prefactor: shared Draft conflict prompt](01-prefactor-shared-draft-conflict.md)
- [16-02: Suggestion tracer: failed Live Verdicts become a system prompt Suggestion](02-suggestion-tracer.md)

**Status:** done

- [x] A Diff read shows the Suggestion's changes against the current Draft, marking each as clean, already applied or a clash
- [x] Apply takes the Draft revision it was reviewed against; for each change, a Draft value equal to the base takes the suggested value, a Draft value equal to the suggested value is left, and any other value is a clash
- [x] Any clash refuses the whole apply with a typed conflict listing each path with its base, Draft and suggested values, and nothing is written
- [x] Otherwise the merged config is written in one Draft save with the given base revision; a stale revision returns the existing stale-Draft conflict, shown with the shared conflict prompt from 16-01
- [x] A Suggestion whose base Version is no longer Live reads as stale; applying it is allowed and the response and Studio say its check was against the old Live
- [x] Applying never Publishes; the Draft revision moves on, so the Publish dialog's Evaluation summary reads stale
- [x] Applying records `agent.suggestion_applied` (Suggestion id and paths, no text) and stamps applied_by and applied_at, shown in the list and detail
- [x] Editors and Owners can delete a Suggestion, recorded as `agent.suggestion_deleted`; applying and deleting are refused on an archived Agent
- [x] Suggestion detail gains "Apply to Draft", which opens the review with any clashes
- [x] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
