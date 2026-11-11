# Ticket template

Copy the block below into the spec's ticket folder as `NN-short-slug.md` (so its links are relative
to `docs/tickets/<spec-folder>/`), add a row to the spec's table in [README.md](./README.md), and
fill in every part. Keep the standing criteria at the end: they apply to every ticket.

```markdown
# NN: Title

**Ticket:** `SS-NN` · **Spec:** [Spec title](../../specs/SS-spec-name-spec.md)

**What to build:** One or two sentences: what a Member can do when this is done, end to end.

**Blocked by:**
- None

**Status:** ready-for-agent

- [ ] One line per observable outcome, each checkable on its own
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
```
