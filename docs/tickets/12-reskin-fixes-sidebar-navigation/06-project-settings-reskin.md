# 06: Project Settings reskin and Embedding Model dialog

**Ticket:** `12-06` · **Spec:** [Reskin fixes and sidebar navigation](../../specs/12-reskin-fixes-sidebar-navigation-spec.md)

**What to build:** A Project's Settings look like Organisation settings: a header and one card per setting, with the Embedding Model changed in a dialog.

**Blocked by:**
- None

**Status:** ready-for-agent

- [ ] Settings opens with a section header and a short description; Embedding Model, OCR and Flagged Chunk mode are each a card with a title and explanation
- [ ] The current Embedding Model shows in mono with Change; Change opens a dialog with the model choice and a warning that every Document is re-embedded, then Cancel and Use this model
- [ ] A running re-embed shows a meter with "N of M Chunks" and which model keeps serving; a failed one shows an error notice with its reason
- [ ] OCR is a labelled toggle row with its hint and current state; the Flagged Chunk mode is two described choices that keep their radio-group semantics
- [ ] Each setting shows the choice at once and is disabled while it saves; an error shows in its card
- [ ] On an archived Project the settings are shown disabled and no Embedding Model change is offered
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns, never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Evidence: light and dark screenshots of the pages touched, wide (1440) and narrow (390), and the axe sweep in both Appearances
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
