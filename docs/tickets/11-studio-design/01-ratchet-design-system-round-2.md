# 01: Palette ratchet and design system round 2

**Ticket:** `11-01` · **Spec:** [Studio design system and reskin](../../specs/11-studio-design-spec.md)

**What to build:** The reskin starts from every feature built so far: `candidate` is merged into `candidate-reskin` first. Then CI stops new Tailwind palette classes appearing in the Studio, and the design system gains every shared pattern the newer views need, so feature work and reskin slices build from the same parts.

**Blocked by:**
- None

**Status:** ready-for-agent

- [ ] The latest `candidate` is merged into `candidate-reskin` before any other change, and every check passes on the merge; the merged commit is named in the evidence
- [ ] `frontend/scripts/palette-ratchet` counts palette-class uses under `apps/studio/src` against a committed `palette-baseline.json`; CI fails when the count rises and prints the new baseline when it falls
- [ ] The ratchet is tested on a fixture tree: a rise fails, a fall passes
- [ ] `Dialog` and `ConfirmDialog` trap focus, close on Escape, return focus to the opener, and use `alertdialog` for destructive confirmations
- [ ] `Toast` announces politely and can offer Undo
- [ ] `Badge` covers Live, Draft, Not live, Archived, Instructions behind, Budget spent, Blocked by guardrail, Low sample and a version chip
- [ ] `CodeBlock` copies its text and confirms it; `Meter` switches accent, flag and danger at 80% and 100% and always prints its value; `Diff` shows line numbers and +/− marks as well as colour
- [ ] `EmptyState`, `Skeleton`, `BulkBar`, `Segmented` (a radio group), `Pagination` and `EditableList` exist with keyboard-complete behaviour
- [ ] Tokens `on-danger` and `chart-1` (`#00897B` light, `#1FA393` dark) are added; the token contract test checks them in both Appearances
- [ ] `docs/design/README.md` and the `studio-reskin` skill describe every new pattern
- [ ] The ticket template says new Studio UI uses the design system
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
