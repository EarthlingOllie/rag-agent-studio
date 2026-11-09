---
name: studio-reskin
description: Reskin the Studio (the signed-in React app in frontend/apps/studio) onto the approved Tidepool design system - tokens, light and dark Appearance, top bar with breadcrumb navigation instead of tabs and side menu. Use when restyling or reskinning any Studio page or the shell, building new Studio UI, replacing slate/Tailwind palette classes, or when told to apply the design system.
---

# Studio reskin

You are moving the Studio from its first-pass styling (Tailwind slate, side menu, tab rows) onto
the approved design system. **Behaviour does not change**: same routes, same data, same
permissions, same accessible names wherever a test or a user relies on them. Only the look and
the navigation chrome change.

## Read first (every time)

1. `docs/design/README.md`: the system: tokens, where the accent goes, layout, navigation.
2. `docs/adr/0013-studio-design-system.md` and the **Appearance** entry in `GLOSSARY.md`.
3. `frontend/apps/studio/src/design/index.ts`: what exists. Use it; don't re-create it.
4. [PATTERNS.md](PATTERNS.md): the code for each slice below.
5. The approved mockups: https://claude.ai/artifact/FmHzJQ49hXshpcyuuhnso5 (page *Direction*).
   If you can't open it, the README's diagrams and tables are the source of truth.

## Rules

- **Tokens only.** No Tailwind palette colours (`slate-*`, `gray-*`, `red-*`, `green-*`,
  `amber-*`, `white`, `black`), no `dark:` variant, no hex or `style={{ color }}`. Use the token
  utilities (`bg-surface`, `text-muted`, `border-line`, `bg-accent`, `text-on-accent`…) or a recipe.
- **Recipes over local constants.** Replace a page's `BUTTON` / `PRIMARY` / `INPUT` / `TAB`
  strings with `button.*`, `field.*`, `table.*`, `text.*`, `notice.*`, `surface.*`, `layout.*`.
  If a recipe is missing something many pages need, add it to `design/recipes.ts` (with a test if it
  has logic) rather than inlining it in a page.
- **Patterns over page-local versions.** Dialogs, confirmations, toasts, badges, code snippets,
  meters, diffs, empty/loading/error states, bulk bars, segmented controls, pagination and editable
  lists already exist in the design system (`Dialog`, `ConfirmDialog`, `useToast`, `Badge`,
  `CodeBlock`, `Meter`, `Diff`, `EmptyState`, `Skeleton`, `BulkBar`, `Segmented`, `Pagination`,
  `EditableList`; see `docs/design/README.md` *Patterns* and PATTERNS.md). Replace a page's own
  version with the pattern, keeping its accessible names where tests rely on them.
- **Data colour.** Charts use `chart-1` only (one series, no legend); never `accent` for data.
- **The ratchet.** `pnpm palette-ratchet` fails if palette classes under `apps/studio/src` rise
  above `frontend/palette-baseline.json`. A slice that removes them commits the lower count it
  prints (`node scripts/palette-ratchet/cli.mjs --write`).
- **Accent sparingly.** Only: the view's one primary button, the current crumb and open switchers,
  Ready dots, citation markers, focus, links in running text, the current item's menu icon.
- **Navigation is the breadcrumb.** No tab rows, no side menu. Sections become a `CrumbSwitcher`.
  Keep every destination reachable and keep role-based hiding (an Editor sees no Members or Audit).
- **Real links.** Switcher items that navigate use `renderLink` with the router's `<Link>`.
- **Never restyle the widget.** `ThemeScope`, `ChatWindow`, `Composer`, `Launcher`,
  `MessageBubble` (packages/ui) and the Theme editor's preview show the Organisation's Theme.
  Reskin the editor's form around the preview, not the preview.
- **Keep the 100% coverage gate** (ADR-0008). Changing markup means updating tests, not deleting
  them. New logic needs tests.
- **Both Appearances.** Check every page you touch in light and dark before you finish.

## Slices (one branch / PR each, in this order)

The reskin is worked on the `candidate-reskin` branch: branch each slice from it and merge it back there, never straight into `candidate`. Each slice is independently shippable. Merge the latest `candidate-reskin` in before starting the next one:
other agents keep adding features to these pages, so small slices conflict least.

| # | Slice | Done when |
|---|---|---|
| R0 | **Foundation**: import `design/tokens.css`, load the fonts, call `initAppearance()` | App looks the same apart from font and background; dark works by system setting |
| R1 | **Shell**: `TopBar` + `Breadcrumb` + Organisation switcher crumb + avatar menu (Profile, Security, Sign out) + `AppearanceToggle`; side menu removed; org-level section switcher (Projects, Settings, Security) | Every org-level page reachable from the breadcrumb; MFA enrolment redirect still works |
| R2 | **Project frame**: Project crumb (switcher of Projects + "All Projects") and section switcher replace the Project tabs; `PageHeader` with Edit details + ⋯ (Archive, Delete); Embedding Model moves into the Settings section | Tabs gone; every Project section reachable; Archive and Delete still work |
| R3 | **Documents**: `StatCard` row, toolbar (search pill, Tag chips, status filter, Upload primary), `table.wrap` table with `Tag`, `Status`, `FlagCount`, ⋯ row menu; Tags panel becomes "Manage tags"; dashed drop zone | Matches the *Documents* mockup in both Appearances |
| R4 | **Agent + Playground**: Agents crumb switcher, Agent name crumb (switcher of Agents); Playground main column; config panel of `Section`s; trace folds under answers; History / Publish in the top bar | Matches the *Agent & Playground* mockup |
| R5 | **Other Project sections**: Document viewer, Instructions (+ Versions), Agents list, Conversations, Analytics, Settings | No palette classes left under `src/projects` |
| R6 | **Organisation settings**: Settings switcher crumb replaces the tabs; General, Members, Credentials, Models, Theme (form only), Audit | No palette classes left under `src/settings` |
| R7 | **Everything else**: Projects list, Security, Profile, signed-out pages (`AuthLayout`), invites, status page, loading and error states | `grep` below finds nothing |
| R8 | **Polish**: narrow-screen breadcrumb collapse, keyboard pass, screenshots refreshed in both Appearances | Checks pass; screenshots committed |

## How to do a slice

1. Read the files you'll touch and their tests. Note every `getByRole`/`getByText` that targets
   navigation or a heading. Those are the behaviours you must keep.
2. Restyle with tokens and recipes. Restructure only where the design requires (tabs → switcher,
   row buttons → ⋯ menu, panels → `Section`).
3. Update unit tests (see *Tests* below), then run, from `frontend/`:
   `pnpm lint && pnpm typecheck && pnpm test && pnpm build`.
4. If the stack runs (`make dev`), run the affected Playwright specs (`pnpm e2e -- --trace off
   <spec>`), including the axe harness (`e2e/harness/axe.spec.ts`), and look at the page in both
   Appearances (`page.emulateMedia({ colorScheme: "dark" })`, or the top bar toggle).
5. Leftover check for the files you touched (must print nothing):
   `grep -nE '(slate|gray|zinc|red|green|amber|blue|white|black)-[0-9]{2,3}|\bdark:|bg-white|text-white' <files>`
   Then `pnpm palette-ratchet` and commit the lowered `palette-baseline.json`.
6. Describe the change in your PR as a reskin; list any behaviour that moved (e.g. "Archive moved
   into the ⋯ menu").

## Tests

Tests describe behaviour through roles and names; keep them that way.

- **Sections were links in a tab nav; now they're items in a switcher menu.** Replace
  `getByRole("navigation", { name: "Project" }).getByRole("link", { name: "Agents" })` with
  opening the switcher and choosing the item:

  ```ts
  await user.click(screen.getByRole("button", { name: /, Project sections$/ }));
  await user.click(screen.getByRole("menuitem", { name: /Agents/ }));
  ```

  In Playwright put this in one helper (`e2e/fixtures/navigation.ts`, `openSection(page, menu,
  item)`) and use it everywhere instead of repeating the clicks; see PATTERNS.md.
- **Role-based hiding**: "Editor sees no Members tab" becomes "the Settings sections menu has no
  Members item". Open the menu and assert the `menuitem` is absent.
- **Headings**: pages keep one `h1` (`PageHeader`); if a test looked for a tab's `h2`, keep it or
  update it to the new heading level deliberately.
- **Row actions in ⋯ menus**: open `getByRole("button", { name: "Actions for <name>" })`, then the
  `menuitem`.
- Don't loosen assertions to make a test pass; if the behaviour changed, the design says so, and
  the test should say the new thing precisely.

## When in doubt

- The mockups and `docs/design/README.md` win over the old screens.
- A design question the docs don't answer (new component, new colour, layout the mockups don't
  show): pick the quietest option that follows the principles, note it in the PR, and add it to
  `docs/design/README.md` so the next page does the same.
