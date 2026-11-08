# Spec 11: Studio design system and reskin

## Problem Statement

The Studio works, but it doesn't look or feel like a product. It was styled page by page as features landed:
- **No shared look.** Tailwind's slate palette is used directly (590 uses across 45 of the 47 UI files), and every page defines its own button, input and tab classes.
- **Navigation crowds the content.** A side menu, a Project header that stacks the description, Archive and the Embedding Model above the tabs, and a second row of tabs inside Organisation settings. Content starts halfway down the screen.
- **Noisy rows.** Each table row carries several underlined text actions (Retry, New edition, Delete), so tables are hard to scan.
- **Long, unstructured pages.** The Agent page is one column of every setting, roughly four screens long, beside the Playground. The Trace opens as a full overlay.
- **No dark mode.** People who work in a dark environment get a bright white app.
- **Patterns invented page by page.** Dialogs, diffs, code snippets, meters, badges, empty and loading states, and charts have each been built ad hoc, or not yet at all.

Features keep landing while this is fixed: seven feature tickets are still open, and Analytics has started. So the reskin can't be a one-off rewrite that freezes everyone else.

## Solution

Adopt one design system, **Tidepool**, and move the whole Studio onto it in small slices, without changing behaviour.

- **Look.** A quiet interface: mist-grey backgrounds, white cards, near-black green text and one sea-glass green accent, taken from colours at the shore. The accent is used only where it means something. Instrument Sans for text, IBM Plex Mono for numbers and ids.
- **Appearance.** A light and a dark Appearance, which follows the system until the Member chooses, and is switched from the top bar.
- **Navigation.** One top bar whose breadcrumb carries every level of navigation: Organisation / Project / section / item. Each level with siblings is a switcher menu. The side menu and both tab rows go away, so pages start with their own title and content.
- **Pages.** Row actions move into ⋯ menus. Agents get four views: Playground, Versions, Embed & limits, Conversations. Settings collapse into sections. The Trace folds under each answer.
- **Shared patterns.** One tested set, defined once in the design system: dialog, confirmation, toast, badges, code block, meter, diff, empty/loading/error states, bulk bar, segmented control, pagination, editable list and the chart style.
- **Delivery.** In order:
  1. A guard that stops new old-style classes being added.
  2. A colour swap that changes no behaviour.
  3. The navigation change, done once and on its own.
  4. One slice per area of the app.

The approved mockups are on the design canvas: https://claude.ai/artifact/FmHzJQ49hXshpcyuuhnso5 (pages *Direction*, *Tab row* and *Patterns & new views*). The rules are in [`docs/design/README.md`](../design/README.md), and the decision is [ADR-0013](../adr/0013-studio-design-system.md).

## User Stories

1. As a Member, I want the Studio to look calm and consistent from page to page, so that it feels like one product and I find things where I expect them.
2. As a Member, I want to choose a light or dark Appearance, so that the Studio is comfortable where I work.
3. As a Member, I want the Studio to follow my system's colour scheme until I choose, so that it matches the rest of my desktop without setup.
4. As a Member, I want my Appearance remembered in this browser, so that I don't pick it again every visit.
5. As a Member, I want the page to open in my Appearance without flashing the other one first, so that switching pages is not jarring.
6. As a Member, I want the breadcrumb to show where I am (Organisation, Project, section, item), so that I always know my place.
7. As a Member, I want to switch Organisation, Project, section or Agent from its crumb, so that I can move sideways without going back up.
8. As a Member, I want the current page marked in the breadcrumb, so that I can tell it from the levels above.
9. As a Member, I want section switchers to be real links, so that I can open a section in a new tab.
10. As a Member, I want number hints (1–6) next to sections in a switcher menu, so that I can learn quick ways around.
11. As an Editor, I want sections I'm not allowed to use (Members, Audit) left out of the menus, exactly as the tabs leave them out today, so that I don't hit pages I can't use.
12. As a Member, I want pages to start with their own title and content, so that I don't scroll past navigation to reach my work.
13. As a Member, I want rare or destructive actions (Archive, Delete) in a ⋯ menu, so that the screen is quiet and I don't hit them by accident.
14. As a Member, I want one clearly primary button per view (Upload, Publish, Send, Save), so that I know what the main action is.
15. As a Member, I want destructive confirmations to name the thing and say what happens, so that I delete only what I mean to.
16. As a Member, I want a short confirmation after a change, with Undo where the action allows it, so that I know it worked and can recover from a slip.
17. As a Member, I want each Project's key figures (Documents, Chunks, flagged chunks, Embedding Model) as cards at the top of Documents, so that I see the Knowledge Base's state at a glance.
18. As a Member, I want document tables with a status dot, Tag pills, a flagged count and a ⋯ menu per row, so that I can scan many Documents quickly.
19. As an Editor, I want the Agent page to give the Playground the main column and put configuration in collapsible sections, so that I can test while I tune.
20. As an Editor, I want each answer's Trace folded under it in the Playground, so that I can check sources without losing the conversation.
21. As an Editor, I want an Agent's Versions as a timeline where I pick any two to compare, so that I understand what changed between them.
22. As an Editor, I want diffs that mark added and removed lines with + and − as well as colour, so that I can read them in any Appearance and without colour vision.
23. As an Editor, I want the Embed snippet with a one-click copy and a launcher choice, so that putting the Agent on a site is quick.
24. As an Editor, I want Allowed Origins as an editable list that warns when it's empty, so that I don't accidentally block every site.
25. As an Editor, I want the Token Budget as a meter that turns to the warning colour near the limit and the danger colour when spent, so that I see trouble coming.
26. As an Editor, I want Conversations as a list beside the transcript, with filters for Agent, Version, dates and Visitors or Playground, so that I can review many Conversations quickly.
27. As an Editor, I want guardrail blocks and answers that cited flagged chunks marked in transcripts, so that I can spot attacks and bad Knowledge Base content.
28. As an Editor, I want Analytics KPIs to show 95% intervals and sample sizes, with small samples visibly marked, so that I don't over-read a handful of ratings.
29. As an Editor, I want the time-series chart to mark when each Version went Live and when Documents changed, so that I can judge whether a Version caused a change.
30. As an Editor, I want every chart to have a table view and a hover readout, so that I can read exact values, including with a screen reader.
31. As a Member, I want empty, loading and error states that say what's happening and what to do next, so that I'm never left looking at a blank page.
32. As a Member who uses a keyboard or screen reader, I want every switcher, menu and dialog to be fully keyboard-operable and announced properly, so that the new navigation doesn't lock me out.
33. As a Member, I want text and controls to meet WCAG AA contrast in both Appearances, so that everything is readable.
34. As a Member on a narrow screen, I want the top bar and breadcrumb to wrap or collapse rather than overflow, so that the Studio still works on a small window.
35. As an Owner, I want the widget and its preview to keep showing my Organisation's Theme, untouched by the Studio's look, so that what I preview is what Visitors see.
36. As a developer adding a feature, I want shared components and class recipes for every common element, so that new UI matches without design decisions.
37. As a developer adding a feature, I want CI to stop me adding Tailwind palette classes, so that the old look doesn't creep back.
38. As a reviewer, I want each slice to come with light and dark screenshots of the pages it changed, so that I can check them against the mockups before merging.

## Implementation Decisions

- **Design system module** (`frontend/apps/studio/src/design`, built in round 1 and opt-in until slice 01):
  - **Colour tokens** in `tokens.css`: CSS custom properties with a light and a dark value, exposed to Tailwind as utilities (`bg-surface`, `text-muted`, `border-line`, `bg-accent`, …). Pages use only token utilities: never palette classes, the `dark:` variant or inline colours.
  - **Class recipes** (`button`, `field`, `surface`, `table`, `text`, `notice`, `layout`) replace each page's local `BUTTON` / `INPUT` / `TAB` strings.
  - **Components:** `TopBar`, `Brand`, `AppearanceToggle`, `Avatar`, `Breadcrumb`, `CrumbSwitcher`, `CrumbText`, `Menu` (keyboard-complete, items can render router links), `PageHeader`, `StatCard`, `Tag`, `Status`, `FlagCount`, `Notice`, `Section`, `Icon`, `WaveMark`.
- **Round 2 additions** (slice 00), to the same module:
  - **Components:** `Dialog` and `ConfirmDialog` (focus trap, Escape, focus returned on close, `alertdialog` for destructive actions); `Toast` (a polite live region, optional Undo); `Badge` (Live, Draft, Not live, Archived, Instructions behind, Budget spent, Blocked by guardrail, Low sample, version chip); `CodeBlock` with copy; `Meter` (accent under 80%, flag from 80%, danger when spent, value always printed); `Diff` (line numbers, +/− marks, soft green and soft red); `EmptyState`; `Skeleton`; `BulkBar`; `Segmented` (radio group); `Pagination`; `EditableList`.
  - **Tokens:** `on-danger` (text on a filled danger button) and `chart-1` (`#00897B` light, `#1FA393` dark). `chart-1` is kept separate from the UI accent: the accent reads too grey for a data mark, and these values pass the palette validator in both Appearances.
- **Appearance** (glossary): light, dark or system. A per-browser choice in `localStorage`, applied to `<html data-appearance>` before first render. It is separate from the widget's Theme and Theme Mode.
- **Navigation model.** The breadcrumb is computed by the Organisation shell from the route, not registered by pages:
  - `Organisation ▾ / Projects`, `Organisation ▾ / Settings ▾ / Members ▾`, `Organisation ▾ / Security`.
  - `Organisation ▾ / Project ▾ / <section> ▾`, where the sections are Documents, Instructions, Agents, Conversations, Analytics and Settings.
  - `… / Documents ▾ / <document>`.
  - `… / Agents ▾ / <Agent> ▾ / <view> ▾`, where the views are Playground, Versions, Embed & limits and Conversations.
  - Profile and Sign out live in the avatar menu.
  - The last crumb is current: accent coloured, with `aria-current="page"`.
  - Each switcher's accessible name is "<label>, <what it holds>" ("Documents, Project sections"), so tests and screen readers can find it whatever is selected.
  - Visibility rules (Owner-only sections, the Require-MFA enrolment-only mode) apply to the menus exactly as they apply to today's tabs.
- **Page anatomy.**
  - **Data pages:** `PageHeader`, an optional `StatCard` row, a toolbar, then a table card with ⋯ row menus.
  - **Agent views:** the Playground is the main column, with a configuration panel of `Section`s. Versions is a timeline plus compare. Embed & limits is cards for the snippet, Allowed Origins, Unavailable text, Token Budget and rate limits.
  - **Conversations:** a list beside the transcript.
  - **Analytics:** a Project section with an Agent filter, KPI cards, and a time-series chart that marks Live History and Document changes.
  - **Signed-out pages:** a centred panel, no top bar.
- **Charts.** One series per chart in `chart-1`, so no legend is needed. Also:
  - a 2px line with a 12% area fill;
  - recessive gridlines in `line-soft`;
  - Live markers drawn as dashed rules with labelled pills;
  - the "Documents changed" period as a `flag-soft` band with an icon and a note;
  - a crosshair and tooltip on hover;
  - a Table view.

  Never two y-axes.
- **Palette ratchet.** A script (`frontend/scripts/palette-ratchet`) counts palette-class uses under `apps/studio/src` (the same pattern as the skill's leftover check) and compares the count with a committed baseline (`palette-baseline.json`). CI fails if the count rises. Each reskin PR lowers the baseline. When it reaches zero, the check becomes "none allowed" and the baseline file is deleted.
- **Colour codemod.** A one-off script applies the skill's class-mapping table (`.claude/skills/studio-reskin/PATTERNS.md`) across the Studio. It changes colours only: no markup or behaviour. Anything ambiguous is left for a human or an agent, and listed in the PR.
- **Behaviour is frozen.** Routes, data, permissions and accessible names stay as they are, unless a slice's ticket names a deliberate change, such as tabs becoming switchers. Moved actions are listed in each PR.
- **Never restyle the widget.** `packages/ui` primitives (`ThemeScope`, `ChatWindow`, `Composer`, `Launcher`, `MessageBubble`) and the Theme editor's preview keep showing the Organisation's Theme.
- **Agent workflow.** Reskin agents follow the `studio-reskin` skill. New feature work uses the design system as soon as slice 01 lands. The ticket template gains that line, and the ratchet enforces it.

## Testing Decisions

- **Good tests** assert what a Member sees and does, by role and accessible name. They never assert class names or colours, except in the token contract test below.
- **Token contract** (exists): `tokens.test.ts` reads `tokens.css` and checks every text-on-background pair for WCAG AA in both Appearances, that light and dark declare the same tokens, that the system-dark and chosen-dark blocks are identical, and that every token is exposed to Tailwind. New tokens (`on-danger`, `chart-1`) join the pair list; `chart-1` is also checked at 3:1 against `surface`.
- **Design system components** are tested at the network seam with Testing Library, like the rest of the Studio. Menus and dialogs get full keyboard paths (open, move, wrap, Home/End, Escape returns focus, Tab closes, click outside). Coverage stays at 100% (ADR-0008).
- **Ratchet** is tested as a script: a fixture tree with known counts, a rise failing, a fall passing and suggesting the new baseline.
- **Navigation migration:**
  - A Playwright helper `openSection(page, menu, item)` (`e2e/fixtures/navigation.ts`) and a Testing Library equivalent (`apps/studio/src/test/navigation.ts`) replace every "click the tab link" step.
  - Role-based hiding becomes "the menu has no such item".
  - About 300 references move to the helpers in the navigation slice, before the tabs are removed.
- **Accessibility:** the axe end-to-end harness runs every reskinned page in both Appearances (`page.emulateMedia({ colorScheme: "dark" })`).
- **Visual evidence:** each slice's evidence folder gets light and dark screenshots of the pages it touched, captured with the existing `docs/screenshots` scripts. They are reviewed against the canvas; there are no automated pixel diffs.
- **Prior art:** `design/*.test.tsx`; the MSW network seam and `renderStudio`; the axe harness in `e2e/harness/axe.spec.ts`.

## Out of Scope

- **The widget's look and the Organisation Theme:** spec 02 and spec 06 own those.
- **New product behaviour.** Analytics content, KPIs and charts come from tickets 07-04 and 07-06; this spec only styles them.
- **Account-level settings:** storing the Appearance on the Member's account, or syncing it across devices.
- **Real keyboard shortcuts.** The menu number hints are labels only; binding the keys is a later polish ticket.
- **Visual regression tooling** (pixel diffs) and a component gallery route.
- **Translation and right-to-left layout.**

## Further Notes

- **Slices** (to be split into tickets under `docs/tickets/11-studio-design/`):

  | # | Slice | Blocked by |
  | --- | --- | --- |
  | 00 | Ratchet + design system round 2 | – |
  | 01 | Foundation: tokens, fonts, Appearance | 00 |
  | 02 | Colour codemod | 01 |
  | 03 | Shell, breadcrumb and navigation test helpers | 02 |
  | 04 | Project frame | 03 |
  | 05 | Documents and Document viewer | 04 |
  | 06 | Instructions, Versions and rollout dialog | 04 |
  | 07 | Agent page and its four views | 04 |
  | 08 | Agents list and bulk actions | 04 |
  | 09 | Conversations and Analytics | 04 |
  | 10 | Organisation settings | 03 |
  | 11 | Signed-out pages, profile, security, status | 03 |
  | 12 | Polish: narrow screens, dark-mode axe, screenshots | 05–11 |

- **Scale.** At the time of writing: 30 routes, 47 UI files, about 11,200 lines, 590 palette uses, 47 unit test files and 50 end-to-end specs. Effort splits roughly 25% colour, 50% structure, 25% tests and checks.
- **Concurrency.** Slices 00–03 run one at a time. Slice 03 touches nearly every page and test, so it runs while no other design slice is open, and it merges `candidate` immediately before landing. Slices 04–11 touch mostly separate files and can run two or three at a time.
- **Pending sign-off.** The round 1 direction is approved. Round 2 (the *Patterns & new views* page) awaits sign-off on three choices:
  - the Agent view switcher as an extra crumb;
  - the `on-danger` and `chart-1` tokens;
  - Analytics as a Project section.

  Confirm or change them before tickets 00 and 07.
