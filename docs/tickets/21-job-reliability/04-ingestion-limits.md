# 04: Ingestion limits: interruption cap, conversion limit and durable retries

**Ticket:** `21-04` · **Spec:** [Job reliability](../../specs/21-job-reliability-spec.md)

**What to build:** A Document that keeps being interrupted becomes Failed with the Failure category "interrupted" instead of restarting for ever, conversion that runs too long is stopped, and an automatic retry always happens even if the broker lost it.

**Blocked by:**
- `21-03`

**Status:** ready-for-agent

- [ ] The third interruption of a Document sets it to Failed with the Failure category `interrupted` and a message that suggests Retry
- [ ] Interruptions are counted apart from provider retries; a manual Retry resets both
- [ ] Conversion that runs past 30 minutes is stopped and the Document is Failed with the existing conversion error; the limit is a setting
- [ ] The time of the next automatic retry is stored on the row and the attempt number is read from the row, never from the message
- [ ] A Document waiting for an automatic retry whose message was lost is retried by the sweeper once its time has passed, and gets no more provider attempts than the maximum
- [ ] The API's Failure category enum gains `interrupted`; the Documents list and Document viewer show it with its message and Retry
- [ ] One Playwright journey: an ingestion is interrupted through a test-only switch on the fake converter, the Document returns to Queued and becomes Ready; axe passes on the Documents list
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
