# 01: Prefactor: shared Draft conflict prompt

**Ticket:** `16-01` · **Spec:** [Suggestions](../../specs/16-suggestions-spec.md)

**What to build:** The Draft editor's "Load their changes / Save mine over theirs" prompt becomes a shared Studio component that another flow writing to the Draft can use; the Draft editor behaves exactly as before.

**Blocked by:**
- None

**Status:** done

- [x] The stale-Draft conflict prompt is a shared, exported Studio component taking the latest Agent from the existing stale-Draft error, with load and overwrite callbacks
- [x] The Draft editor uses it, and its existing conflict tests pass unchanged
- [x] The component has its own network-seam tests for both choices
- [x] No behaviour or API change
- [x] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
