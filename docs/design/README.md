# Studio design system

The approved look for the Studio (the signed-in app where Members build Agents). It is called
**Tidepool**: a quiet, minimal interface with mist-grey backgrounds and a single sea-glass green
accent that marks where you are and what to press, taken from colours you find at the shore. It
comes in a light and a dark **Appearance**.

- Approved concept (design canvas, pages *Direction* and *Tab row*): https://claude.ai/artifact/FmHzJQ49hXshpcyuuhnso5
- Decision records: [ADR-0013](../adr/0013-studio-design-system.md), amended for navigation by [ADR-0014](../adr/0014-sidebar-navigation.md)
- Code: `frontend/apps/studio/src/design/` (import from `../design`)
- Reskinning a page: the `studio-reskin` skill (`.claude/skills/studio-reskin/`)

This is the Studio's own look. It is separate from an Organisation's **Theme**, which styles the
embedded widget (`frontend/packages/ui`). Never apply Studio tokens to the widget or its preview.

## Principles

1. **Quiet by default.** The canvas is mist, the content sits on white cards, the text is near-black
   green. Most of a screen has no colour at all.
2. **One accent, used sparingly.** Sea-glass green appears only where it means something (see
   *Where the accent goes*). If a screen has more than a few green things, remove some.
3. **Navigation you can see.** Every place a Member can go is a link in the sidebar beside the
   page, the current one highlighted; the top bar's breadcrumb is a plain path that says where
   they are. Pages start with their own title and content, with one heading (ADR-0014).
4. **Secondary actions hide.** Row actions go in a "⋯" menu, rare page actions (Archive, Delete) in
   the page's "⋯" menu. Each view has at most one primary (filled) button.
5. **Both Appearances, always.** Every screen works in light and dark. Tokens switch automatically;
   nothing is styled for one Appearance only.

## Colour tokens

Use the Tailwind utility for a token (`bg-surface`, `text-muted`, `border-line`…). Never use
Tailwind's palette (`slate-700`, `red-800`, `green-50`) or the `dark:` variant.

| Token | Use | Light | Dark |
| --- | --- | --- | --- |
| `canvas` | Page background | `#F3F6F6` | `#0E1615` |
| `surface` | Cards, top bar, panels, inputs | `#FFFFFF` | `#152120` |
| `sunken` | Hover, selected menu item, segmented trays, info notices | `#E9EFEE` | `#1C2B2A` |
| `line` | Card and bar borders | `#E1E8E7` | `#233331` |
| `line-soft` | Row dividers inside a card | `#EEF2F1` | `#1E2C2B` |
| `field` | Input and secondary-button borders, dashed drop zones | `#D3DEDC` | `#2E4240` |
| `ink` | Body text, titles | `#15201F` | `#E3ECEA` |
| `ink-2` | Labels, secondary text that must stay strong | `#36423F` | `#C2D0CD` |
| `muted` | Descriptions, metadata, ancestor crumbs, icons | `#536260` | `#93A5A2` |
| `accent` | Primary buttons, current crumb, focus ring, Ready dot, links | `#2C6E6A` | `#6FB8B1` |
| `accent-hover` | Primary button hover | `#245B58` | `#86C7C1` |
| `on-accent` | Text on `accent` | `#FFFFFF` | `#0B1A19` |
| `accent-soft` | Current sidebar link, open switcher, success notice, assistant avatar | `#DCEBE9` | `#1F3836` |
| `accent-ink` | Text on `accent-soft` | `#1F4F4C` | `#A9DCD6` |
| `sand` | Tag pills, Draft badge | `#EDE6D6` | `#3A3326` |
| `sand-ink` | Text on `sand` | `#5A4A2A` | `#E6D7B5` |
| `flag` | Flagged chunks, warnings | `#8A4B0F` | `#E8A062` |
| `flag-soft` | Warning notice background | `#F7EBDD` | `#3A2A1A` |
| `danger` | Errors, destructive actions | `#A3372A` | `#F08C7A` |
| `danger-soft` | Error notice background, danger hover, removed diff lines | `#F8E4E0` | `#3A1F1B` |
| `on-danger` | Text on a filled `danger` button (a destructive `ConfirmDialog`) | `#FFFFFF` | `#1A0F0D` |
| `chart-1` | Data only: chart lines, bars and areas. Never UI | `#00897B` | `#1FA393` |

Every text pair above meets WCAG AA (4.5:1) in both Appearances, and `chart-1` meets 3:1 against
`surface` and `canvas` as a data mark; `design/tokens.test.ts` checks this against `tokens.css`, so a
token change that breaks contrast fails the build.

`chart-1` is kept apart from `accent` on purpose: the accent reads too grey as a data mark, and the
accent keeps meaning "where you are, what to press". Use `chart-1` for data and nothing else.

### Where the accent goes

- The primary button of a view (Upload, Publish, Send, Save).
- The **current** link in the sidebar (soft fill) and the current crumb in the breadcrumb (text).
- The current tab's underline in a `TabRow`.
- The current item's icon in an open menu.
- Status "Ready" dots, citation markers, the "cited" chunk in a trace.
- Focus rings and links in running text.
- The wave mark.

Nowhere else: not headings, not table text, not borders, not backgrounds of whole sections.

## Type

- **Instrument Sans** for everything (`font-sans`), **IBM Plex Mono** for numbers, ids, file
  sizes, token counts, model names and code (`font-mono`).
- Page title: `text.title` (32px, medium, tight tracking). One per page.
- Section heading: `text.heading` (18px medium). Card heading: `text.subheading`.
- Body 15px; secondary 13–14px in `muted`; table text 14px; numbers in table cells 13px mono.

## Shape and space

- Cards and panels: `rounded-2xl` (16px), 1px `line` border, no shadow.
- Inputs: `rounded-xl` (12px), 40px tall. Buttons and pills: fully rounded, 36px tall.
- Selects: every single-value select draws the design system's chevron-down (the `--ds-chevron`
  token, stroked in `muted` for each Appearance) instead of the browser's arrow, from one base rule
  in `tokens.css`. The chevron sits as far from the right edge as the text from the left (each
  select recipe sets `--select-inset` to its left padding), the right padding never drops below
  36px, and a disabled select dims with its chevron. Use `field.select` in forms, `field.pill` in
  toolbars and `field.selectCompact` in table cells; never a select class string of a page's own.
- Menus and popovers: `rounded-2xl`, soft shadow (`surface.popover`).
- Page content: max width 1160px, 32px side padding (16px on phones), 28px between blocks.

## Layout

```
┌ TopBar ─────────────────────────────────────────────────────────────────────┐
│ ≈ Studio   Northwind Handbook / Agents / HR helper     [Saved] [Publish] ◐ (NN)│
├ Sidebar ──────────┬─────────────────────────────────────────────────────────┤
│ Northwind ▾       │  PageHeader: title + description      [Edit details] [⋯] │
│ ▣ Projects        │  [StatCard] [StatCard] [StatCard] [StatCard]             │
│ ◔ Cost            │  toolbar: (search) (All)(HR)(Products)      [⤒ Upload]   │
│ ⚙ Settings        │  ┌ table.wrap ───────────────────────────────────────┐   │
│ ───────────────── │  │ ☐ Name             Tags    Status   Chunks   ⋯   │   │
│ ▣ Northwind HB ▾  │  └───────────────────────────────────────────────────┘   │
│ ▤ Documents       │                                                          │
│ ✎ Instructions    │                                                          │
│ ☺ Agents          │                                                          │
│ …                 │                                                          │
└───────────────────┴──────────────────────────────────────────────────────────┘
```

- The sidebar is about 240 px wide and stays in place while the page scrolls; the page keeps its
  1160 px column, centred in the space beside it.
- Below `md` (768 px) the sidebar is a drawer behind the top bar's "Open navigation" button, and
  the page gets the full width.

### Navigation: the sidebar

The sidebar (`Sidebar`, the navigation landmark named "Studio") is how a Member moves around. It
is computed from the page's address and the Member's session; pages register nothing
(`shell/StudioSidebar.tsx`).

| Where you are | Sidebar | Breadcrumb |
| --- | --- | --- |
| Projects list | Org ▾; **Projects**, Cost, Settings | **Projects** |
| Cost | Org ▾; Projects, **Cost**, Settings | **Cost** |
| Organisation settings | Org ▾; Projects, Cost, **Settings** (the areas are a `TabRow` under the header) | Settings / **Members** |
| Security, Profile (from the account menu) | Org ▾; Projects, Cost, Settings (none current) | **Security** |
| A Project section | Org ▾; Projects, Cost, Settings; Project ▾; **Documents**, Instructions, Agents, … | Project / **Documents** |
| A Document | … Project ▾; **Documents**, … | Project / Documents / **handbook.md** |
| An Agent | … Project ▾; …, **Agents**, … (its views are a `TabRow` under its header) | Project / Agents / **HR helper** |

- **Top to bottom:** the Organisation switcher (`sidebarSwitcher`, a `Menu` of the Member's
  Organisations; a Member of one sees its name as plain text, `SidebarTitle`), then the
  Organisation's links (`SidebarGroup` "Organisation sections": Projects, Cost for Owners,
  Settings). Inside a Project: a `SidebarDivider`, the Project switcher (the open Projects, then
  All Projects; archived Projects are opened from the Projects list) and the Project's six sections
  (`SidebarGroup` "Project sections": Documents, Instructions, Agents, Conversations, Analytics,
  Settings), each with its icon (`SidebarLabel`). No link carries a number or other hint.
- **Current link:** `sidebarLink` gives the current one (`aria-current="page"`) the soft accent
  fill. A section stays current on its inner pages: the Document viewer under Documents, an Agent
  under Agents, a Conversation under Conversations. Projects is not current inside a Project.
- **Who sees what:** Cost is left out for anyone but an Owner. Under the Require MFA policy, until
  the Member enrols, the sidebar offers only Security.
- **Account menu:** the avatar at the right of the top bar is the only home of Profile, Security
  and Sign out; they are not in the sidebar.
- **Tab rows** (`TabRow`, `tabLink`) hold a page's own views under its header, each a link and a
  page of its own: an Agent's views ("Agent views") and Organisation settings' areas
  ("Organisation settings": General, Credentials, Models, Theme, and Members and Audit for Owners).
  The current tab has `aria-current="page"`.
- **Drawer:** below `md` the sidebar is hidden until "Open navigation" (`SidebarButton`) opens it as
  a modal dialog named "Navigation" over the page. Opening it focuses the current link (or the
  first); Tab and Shift+Tab stay inside; Escape, a press outside it or following a link closes it
  and returns focus to the button. A switcher's own menu takes Escape first.

### Navigation: the breadcrumb

The top bar's breadcrumb (`Breadcrumb`, named "Breadcrumb") is a plain path of links that says
where the Member is: from the Organisation's page they are under down to the page they are on
(`shell/StudioBreadcrumb.tsx`, computed from the address). It never opens a menu.

- Each crumb is a router link styled `crumbLink`: ancestors `muted`, the current page (the last
  crumb, `aria-current="page"`) in `accent`. A crumb leads back up a level: the Project to its
  Documents, a section to its list, Settings to General.
- The Organisation is not a crumb: it is named at the top of the sidebar.
- An Agent is the last crumb on every one of its views (the tab row says which); until the Agent,
  Document or Project has loaded, the path ends at the level above it.
- Below `md` only the last two crumbs are shown (`Breadcrumb` hides the rest and the separator
  before the first one shown), and the top bar's mark drops its "Studio" name (`Brand compact`),
  so the mark and the path share one row. There is no "…" fold.
- A long name is cut short with an ellipsis rather than wrapping. The page's own actions
  (`TopBarActions`) join that row while it leaves the path at least 12rem, and drop under it
  otherwise (an Agent's History and Publish on a phone).

### Pages

- **List and data pages** (Documents, Agents, Conversations, Members, Credentials, Audit):
  `PageHeader`, optional `StatCard` row, a toolbar, then a `table.wrap` card. Row actions in a ⋯
  `Menu` (`button.iconBare`), destructive items marked `danger`.
  - **Documents** (as built in 11-06): inside a Project the `PageHeader` is the Project's, so the
    section starts at the Knowledge Base figures (Documents / quota, Chunks, Flagged chunks,
    Embedding Model). The toolbar is search, Tag chips (a `Segmented` "Filter by Tag", All first),
    Manage tags (opens the Tags `Dialog`), then Clear filters, the status filter and Upload, the one
    primary. A quiet drop zone sits under it. Rows show Name, Type, Tag pills, a status dot, Chunks,
    `FlagCount` and Size; Retry, New edition, Edit Tags and Delete are in the ⋯ menu. A selection
    shows `BulkBar` with Add Tag and Remove Tag menus. Changes are confirmed with a toast, Delete
    asks in a `ConfirmDialog`, and refusals, a full quota and failed Documents are `Notice`s.
  - **Document viewer**: the breadcrumb ends with the Document's name; a header with its details
    and Download original; the markdown in a panel beside the Chunks, each on a card, flagged ones
    edged in `flag` and badged Flagged, paged with `Pagination`.
- **Projects list** (built in 12-03): the Organisation's page, laid out like the Agents list.
  `PageHeader` "Projects" (the page's one h1, "Each Project holds the Documents its Agents answer
  from.") with New Project, the one primary, on the right; it is hidden while Archived is shown.
  The toolbar is a `Segmented` "Projects shown" (Active / Archived). Active Projects are a
  `table.wrap` card: the name as `table.link`, the Description muted and cut to one line (the full
  text in its `title`), then Documents and Agents in `table.thNumeric` / `table.tdNumeric`.
  Archived Projects are a card with the archived date in mono and, for Owners, a secondary
  Restore in the row, confirmed by a toast; a line above says Owners restore them (or that only
  Owners can). Loading is a `Skeleton`, a failed load an error `EmptyState`, and no Projects or no
  archived Projects an `EmptyState`. After a Project is deleted, "… is being deleted permanently."
  is a success `Notice`.
- **Project details dialog** (12-02): New Project and a Project header's Edit details open one
  `Dialog` (no corner ✕) holding a form named "New Project" or "Project details": `FormError`,
  Name (`field.input`, required) and Description (`field.textarea`), then Cancel and the primary
  "Create Project" / "Save". The opening button stays where it is and gets focus back on Cancel or
  Escape; a saved edit closes the dialog with a toast. Nothing is edited inline under the header.
- **A Project section** (built for Agents in 11-09) is the same under the Project's own header:
  `PageHeader level={2}` (the Project keeps the page's one h1) with the section's primary action
  on the right (New Agent opens a `Dialog`). The Agents list is a `table.wrap` card with a
  `Segmented` Active / Archived filter, the Live state as `Badge`s (Live + version chip, Not
  live, Draft, Budget spent, Blocked by guardrail) and checkboxes that bring up the `BulkBar`.
- **Conversations** (built in 11-10): the section heading, then a toolbar of pill filters
  (`field.filter` labels over `field.pill` selects and dates: Agent, Version, From, To, then the
  Visitors / Playground / Both `Segmented`, Feedback, Rating, Guardrail). Under it the list (a
  `surface.card` of compact items: the first question as the link, then mono time, Agent, a
  Playground pill, Version numbers and labelled counts; the open one on `accent-soft`) with
  `Pagination` and the "Page n of m" line, and beside it the transcript in a `surface.panel`:
  questions as bubbles on the right, answers beside an avatar with a Version chip (or Draft), a
  `blocked` badge when the input Guardrail refused, the feedback note on `sunken`, and the Trace
  folded under each answer (`TraceFold`). Delete Conversation (Owners) confirms in a destructive
  `ConfirmDialog`. Before one is chosen the transcript side is an `EmptyState`. An Agent's
  Conversations view is the same, fixed to the Agent (no Agent filter).
- **Analytics** (built in 11-10): the section heading, one toolbar (Agent, Version, From, To; the
  Agent is in the URL as `?agent=`), the range line, then KPI cards (`text-[13px]` muted title,
  mono value, interval and n under it; a small sample is dashed and muted with a `lowSample` badge
  whose title says why), Compare two Versions (`table.wrap`, changed rows on `flag-soft`), and
  Over time (the chart; see *Charts*).
- **Organisation cost** (built in 12-04): `PageHeader` ("Organisation cost", the frozen-prices
  sentence as its description), then a toolbar: "Break down by" as a `Segmented` (Project /
  Agent) and From and To as `field.filter` / `field.pill` date filters. The period line sits under
  it, then the `StatCard` row (Total, Visitors, Playground; a list named "Spend for the period")
  and the `table.wrap` card (a focusable region, so it scrolls sideways inside the card on a phone):
  names in `table.td`, amounts in `table.thNumeric` / `table.tdNumeric` (right-aligned, mono), and
  the "All Projects" / "All Agents" total row set apart on `sunken` above a `line` border. Nothing
  spent is an `EmptyState`; bad dates (the 422) and a failed load are `Notice tone="error"`;
  loading is a `Skeleton`. An Editor sees an `EmptyState`, "Only Owners see the Organisation's
  spend", under the header. The Audit page's filters use the same `field.filter` / `field.pill`.
- **Agent page** (tabs built in 12-10): the Project's `PageHeader` is left out, so the Agent's
  `PageHeader` is the page's one h1: its name, then (`beside`) a ▾ Agent switcher (a `Menu` of the
  Project's open Agents, `button.iconBare`, named "<Agent>, Agents") and its `Badge`s (Live with
  the Version chip, or Not live; Draft while there are unpublished changes); on the right
  "Analytics for this Agent" (a ghost link to Analytics filtered to it) and a ⋯ menu (Discard
  Draft, Archive, or Delete permanently on an archived Agent). Under it a `TabRow` "Agent views"
  of `tabLink`s (Playground, Versions, Embed & limits, Conversations; the current one has
  `aria-current="page"`, an `accent` underline and `ink` text, and Conversations stays current on
  a Conversation opened from it), then the view. An archived Project's notice stays above it.
  - **Playground**: the Playground is the main column (max 720px, centred); configuration is a
    right-hand panel (360–420px) of collapsible `Section`s (Behaviour open; Retrieval, Experience,
    Guardrails collapsed with a mono summary; a section the API refused a setting in opens). The
    trace folds open under each answer (a `<details>` card; the cited chunk in `accent`, flagged
    ones in `flag`).
  - **Versions**: the Live History as a timeline (Revert in the Live Version's ⋯ menu), the
    Versions (Start Draft from in each one's ⋯ menu), then Compare with From/To and `Diff`s.
  - **Embed & limits**: cards for the `CodeBlock` snippet with its launcher, Allowed Origins
    (`EditableList`), Unavailable text, Token Budget (`Meter`), rate limits and the Theme override.
  - Page actions (Saved state, History, Publish) sit in the top bar's right side, portalled with
    `TopBarActions` (`shell/TopBarActions.tsx`). Publish opens a `Dialog`.
- **Settings and forms**: a `surface.panel` per group, labels above fields, one primary button.
  Organisation settings (built in 11-11) keep one `PageHeader` ("Organisation settings"); the
  area (General, Credentials, Models, Theme, and Members and Audit for Owners) is a `TabRow`
  "Organisation settings" under it (`shell/settingsNavigation.tsx`). Lists there (Members, pending invites, Credentials,
  the price table, the Audit log) are `table.wrap` cards; long ones page with `Pagination`.
  Saved changes confirm with a toast; a destructive one asks with `ConfirmDialog` first.
  - **Members** (invite dialog in 12-05): the Members heading row carries **Invite someone**
    (`button.primary`) on the right; it opens a `Dialog` (no corner ✕) holding the form
    "Invite someone": `FormError`, Email (`field.input`), Role (`field.select`), "Email the
    invite link" (`field.checkbox`), then Cancel and the primary Invite. Nothing about inviting is
    inline. On success the dialog closes, a toast confirms, and the copy-link panel
    (`surface.panel`, "New invite") shows above Pending invites; New link on a pending invite
    shows the same panel. Cancel or Escape returns focus to Invite someone.
- **Project Settings** (built in 12-06): `PageHeader level={2}` ("Settings", one line on what they
  control), then a `surface.panel` card per setting with an h3 title and its explanation:
  - **Embedding Model**: the active model in mono on a `sunken` row with **Change** (named "Change
    Embedding Model"), which opens a `Dialog` "Change the Embedding Model": the model select, a
    warning notice that every Document is re-embedded (an info notice when the Project has none),
    then Cancel and **Use this model**. A running Re-embed is a progress `Meter` ("N of M Chunks")
    under a status line naming the model that keeps serving; a failed one is an error `Notice`.
  - **OCR**: a labelled checkbox row on `sunken` (the hint is its description) and a status line.
  - **Flagged Chunks**: a `radiogroup` of two bordered choices, each a title and a one-line
    description; the chosen one takes `accent-soft`.

  Each setting shows the choice at once, is disabled while it saves and shows a refusal in its
  card. On an archived Project the header says the settings can't be changed, every control is
  disabled and the Embedding Model card is left out.
- **Project Instructions** (built in 11-07): a `surface.panel` each for the Draft (the markdown
  editor with its character count, Save Instructions as a secondary button and the conflict offer
  as a warning notice), Publish (the Note and **Publish Instructions**, the page's one primary),
  Agents (the "N Agents behind" summary and a `table.wrap` of version chips with an Instructions
  behind badge) and Versions (a timeline, newest first, each a version chip with the `current`
  badge on the Current Version, then Compare: two selects and `Diff`). Reverting asks with a
  destructive `ConfirmDialog`. The rollout offer after publishing and the bulk-revert offer after
  reverting are `Dialog`s: every eligible Agent pre-selected, Draft changes badged `draft`, and
  the results counted ("2 succeeded, 0 skipped, 1 failed") then listed per Agent.
- **Signed-out pages** (sign in, sign up, MFA, reset, invite, the status page, and the shell's
  own loading and error states before the session is known): a centred `surface.panel` on the
  canvas with the wave mark, no top bar (`SignedOutFrame` in `auth/AuthLayout.tsx`). Form errors
  are `Notice tone="error"` (`ErrorNotice`); links inside the panel are accent and underlined.
- **Profile and Security**: `PageHeader`, then a `surface.panel` card per form. MFA enrolment
  shows the QR code and its fallback key on an inner card, and recovery codes as a grid of mono
  chips on their own card.
- **Status page**: a `Status` dot per dependency (Ready for OK, Failed for Unavailable, Working
  for Checking).

## Components (`frontend/apps/studio/src/design`)

| Export | What |
| --- | --- |
| `tokens.css` | The tokens, the Appearance switch, base body styles and focus ring |
| `button`, `field`, `surface`, `table`, `text`, `notice`, `layout` | Class recipes |
| `TopBar`, `Brand`, `AppearanceToggle`, `Avatar` | The frame |
| `Sidebar`, `SidebarButton`, `SidebarGroup`, `SidebarLabel`, `SidebarDivider`, `SidebarTitle`, `sidebarLink`, `sidebarSwitcher` | The sidebar and its drawer (see *Navigation: the sidebar*) |
| `Breadcrumb`, `crumbLink` | The top bar's plain path of links (see *Navigation: the breadcrumb*) |
| `TabRow`, `tabLink` | A page's own views as a row of tab links under its header (an Agent's views, Organisation settings' areas) |
| `Menu`, `MenuItem`, `MenuLinkProps` | Switchers and ⋯ menus, keyboard-complete |
| `PageHeader`, `StatCard`, `Tag`, `Status`, `FlagCount`, `Notice`, `Section` | Content |
| `Dialog`, `ConfirmDialog` | Modal dialogs and confirmations (see *Patterns*) |
| `ToastProvider`, `useToast` | Confirmation after a change, with Undo |
| `Badge` | Live, Current, Draft, Not live, Archived, Instructions behind, Budget spent, Blocked by guardrail, Low sample, Flagged, Working, Check failed, Version chip |
| `CodeBlock`, `Meter`, `Diff`, `diffLines` | Copyable code, usage against a limit, line diffs |
| `EmptyState`, `Skeleton` | Empty, error and loading states |
| `BulkBar`, `Segmented`, `Pagination`, `EditableList` | Selections, option groups, paging, in-place lists |
| `Icon`, `WaveMark` | Line icons (`documents`, `agents`, `more`, `upload`…) and the mark |
| `useAppearance`, `setAppearance`, `initAppearance` | Light / dark / system, remembered per browser |

## Appearance

The Member chooses light or dark with the toggle in the top bar; until they choose, the Studio
follows the system setting. The choice is stored in `localStorage` (`studio.appearance`) and
applied to `<html data-appearance>` before the first render by `initAppearance()`. It belongs to
the browser, not the Member's account.

## Patterns

Round 2 adds the patterns the newer views share. Use these instead of building your own. Each is
keyboard-complete and tested in `design/*.test.tsx`.

### Dialogs: `Dialog` and `ConfirmDialog`

- A `Dialog` is modal: it takes focus (its first control), keeps Tab and Shift+Tab inside, closes on
  Escape, its ✕ or a click on the scrim, and returns focus to the control that opened it. It has a
  title (`text.heading`), an optional one-line description and a footer of buttons, primary last.
- A `ConfirmDialog` asks before an action. The children name the thing and say what will happen
  ("Its 42 chunks are removed and Agents stop citing it."). Pass `destructive` for Delete, Archive
  and the like: it becomes an `alertdialog`, a stray click outside does not dismiss it, focus starts
  on Cancel and the confirm button is the filled danger button (`button.dangerFilled`, `bg-danger
  text-on-danger`). `busy` disables both buttons while the action runs.
- When a confirmation asks for more than a click (type a Project's name to delete it for good),
  put the field and any refusal in `body`, under the description, and pass `confirmDisabled` until
  it is ready. The body's first field takes focus; wrap it in a `<form>` so Enter confirms.

### Toast

- Wrap the app in `ToastProvider`; call `useToast().show("Archived HR helper.", { onUndo })` after a
  change. One toast at a time, bottom centre, gone after 8 seconds or on Dismiss.
- The message is read out by a polite live region that is always in the page. Offer Undo whenever the
  action can be reversed; it runs once and closes the toast.
- Errors are not toasts: show them where they happened, with `Notice tone="error"`.
- Today the provider wraps Organisation settings only (`OrganisationSettingsLayout`, 11-11), so
  its always-present live region doesn't sit beside other pages' own status messages. Move it up
  to wrap the app when another section needs toasts; an inner provider still works.

### Badge

`<Badge kind="…" />` with the same words everywhere:

| `kind` | Words | Colour |
| --- | --- | --- |
| `live` | Live | `accent-soft` with an accent dot |
| `current` | Current (the Current Version of the Project Instructions) | `accent-soft` |
| `draft` | Draft | `sand` |
| `notLive` | Not live | `sunken`, `muted` |
| `archived` | Archived | `sunken`, `muted` |
| `instructionsBehind` | Instructions behind | `flag-soft`, `flag` |
| `budgetSpent` | Budget spent | `danger-soft`, `danger` |
| `blocked` | Blocked by guardrail | `danger-soft`, `danger` |
| `lowSample` | Low sample | `flag-soft`, `flag` |
| `flagged` | Flagged (a Chunk the ingestion scan flagged) | `flag-soft`, `flag` |
| `checkPassed` | Working (a Provider Credential's last check passed) | `accent-soft` with an accent dot |
| `checkFailed` | Check failed (the reason goes beside it) | `danger-soft`, `danger` |
| `version` | `v3` (read as "Version 3") | mono chip, `line` border |

`title` adds a hover explanation ("Fewer than 30 rated answers"). The words carry the meaning;
colour only repeats it.

### CodeBlock

Code to paste elsewhere (the Embed snippet): mono on `sunken`, with a Copy button that copies the
exact text, turns into "Copied" for two seconds and announces "<label> copied.". If the browser
refuses, an alert says to select and copy by hand.

### Meter

How much of a limit is used (Token Budget, Document quota): a bar in `accent` under 80%, `flag`
from 80% and `danger` once spent, with the value always printed beside it ("8,200 / 10,000
tokens"). It is a `meter` role with the value as text, so the colour is never the only signal.
A `progress` meter (a Re-embed's Chunks) shows how far work has got, so it stays `accent` all the
way.

### Diff

Line-by-line change between two texts (system prompt, Project Instructions, Agent config): both
sides' line numbers, a + or − mark on added and removed lines (read as "Added"/"Removed"), added
lines on `accent-soft`, removed on `danger-soft`, and a "2 added, 1 removed" summary ("No changes"
when equal). `diffLines(before, after)` gives the same diff as data.

### Empty, loading and error states

- `EmptyState`: an icon, a title saying what is not here, a sentence saying what to do, and the next
  step's button ("No Documents yet. Upload a file to start the Knowledge Base." [Upload]).
- `EmptyState tone="error"`: the same shape, announced as an alert, for a list that failed to load.
- `Skeleton`: grey bars where content is loading, announced once as "Loading…" (pass a `label`
  such as "Loading Documents"). Use it for the first load; keep stale content on screen on refetch.

### Charts

As built for Analytics' Over time (`projects/TimeSeriesChart.tsx`, Recharts):

- One series per chart in `chart-1` (`var(--ds-chart-1)`): a 2px line with a 12% area fill, so no
  legend is needed. Never two y-axes: a second metric is a second chart (or the Metric select).
- Gridlines are horizontal only, in `line-soft`; ticks in `muted`, 12px.
- Live markers are dashed rules (`muted`, 4 3) with a mono pill label on `surface` at the top
  ("v2", or "v2, v1" for several changes in one period); the same changes are listed under the
  chart.
- Documents changed during the range: a `flag-soft` band over the plot with a warning icon and
  "Documents changed", and the `notice.warning` note under the chart.
- Hover: a crosshair (a dashed vertical cursor, a dashed horizontal rule and a ringed dot at the
  point) and a readout on `surface.popover`, `role="status"` "Chart readout": the period (mono), the
  value and its n. Days with no data read "No data".
- A `Segmented` "Show as: Chart / Table" swaps in the Table view (`table.wrap`, numbers in mono),
  which also serves screen readers. The `figure` is named by its caption.

### Selections and lists

- `BulkBar`: appears above a table while rows are selected: "3 Agents selected", the actions, Clear
  selection. A toolbar: arrow keys move between its buttons, Escape clears. A `Menu` in the bar
  (Add Tag ▾) keeps its own keys while open.
- `Segmented`: a few mutually exclusive options side by side (Visitors / Playground / All). A radio
  group with one Tab stop; arrows move and choose, Home and End jump.
- `Pagination`: Previous, page numbers (first, last, current and its neighbours, "…" between) and
  Next, in a named `navigation`. Hidden for a single page.
- `EditableList`: a short list edited in place (Allowed Origins). Enter or Add adds; blanks,
  duplicates and anything `validate` refuses are rejected with the reason under the input; Escape
  clears; each item has a Remove button and focus moves to the next one after a removal. Give it
  an `emptyWarning` when an empty list has a consequence ("No site can embed this Agent until you
  add an origin.").

## Keeping the old look out: the palette ratchet

CI runs `pnpm palette-ratchet` (from `frontend/`, also the last step of `make test-frontend`). It
counts palette-class uses under `apps/studio/src` with the same pattern as the reskin skill's
leftover check (the `dark:` variant counts only as `dark:` directly followed by a class, so a
Theme colour's `{ light, dark }` key is not counted). The count reached zero in ticket 11-13 and
`frontend/palette-baseline.json` was deleted: with no baseline file none are allowed, and any
palette class fails the check. While the reskin was under way it compared the count with the
baseline:

- **Higher**: the check fails and lists the files. Use tokens and recipes instead.
- **Lower**: the check passes and prints the new count. Commit it
  (`node scripts/palette-ratchet/cli.mjs --write` writes it; it never raises the baseline).
- When the count reaches zero, delete the baseline file: with no file, none are allowed.

## Don't

- Don't use raw colours, Tailwind palette classes, `dark:`, or inline `style` colours.
- Don't add menus to the breadcrumb or a second home for a destination; add a sidebar link, or a
  tab to the page's own `TabRow`.
- Don't put more than one primary button in a view, or colour whole sections green.
- Don't use emoji or filled icons; use `Icon`.
- Don't build your own dialog, toast, badge, meter, diff, empty state or pager: use the pattern.
- Don't use `chart-1` for UI, or `accent` for data.
- Don't restyle the widget preview (`ThemeScope`, `ChatWindow`): it shows the Organisation's Theme.
