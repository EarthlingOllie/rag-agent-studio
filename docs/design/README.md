# Studio design system

The approved look for the Studio (the signed-in app where Members build Agents). It is called
**Tidepool**: a quiet, minimal interface with mist-grey backgrounds and a single sea-glass green
accent that marks where you are and what to press, taken from colours you find at the shore. It
comes in a light and a dark **Appearance**.

- Approved concept (design canvas, pages *Direction* and *Tab row*): https://claude.ai/artifact/FmHzJQ49hXshpcyuuhnso5
- Decision record: [ADR-0013](../adr/0013-studio-design-system.md)
- Code: `frontend/apps/studio/src/design/` (import from `../design`)
- Reskinning a page: the `studio-reskin` skill (`.claude/skills/studio-reskin/`)

This is the Studio's own look. It is separate from an Organisation's **Theme**, which styles the
embedded widget (`frontend/packages/ui`). Never apply Studio tokens to the widget or its preview.

## Principles

1. **Quiet by default.** The canvas is mist, the content sits on white cards, the text is near-black
   green. Most of a screen has no colour at all.
2. **One accent, used sparingly.** Sea-glass green appears only where it means something (see
   *Where the accent goes*). If a screen has more than a few green things, remove some.
3. **Content first.** Navigation lives in the top bar's breadcrumb, not in tab rows or side menus,
   so pages start with their own title and content.
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
| `accent-soft` | Open switcher, success notice, assistant avatar | `#DCEBE9` | `#1F3836` |
| `accent-ink` | Text on `accent-soft` | `#1F4F4C` | `#A9DCD6` |
| `sand` | Tag pills, Draft badge | `#EDE6D6` | `#3A3326` |
| `sand-ink` | Text on `sand` | `#5A4A2A` | `#E6D7B5` |
| `flag` | Flagged chunks, warnings | `#8A4B0F` | `#E8A062` |
| `flag-soft` | Warning notice background | `#F7EBDD` | `#3A2A1A` |
| `danger` | Errors, destructive actions | `#A3372A` | `#F08C7A` |
| `danger-soft` | Error notice background, danger hover | `#F8E4E0` | `#3A1F1B` |

Every text pair above meets WCAG AA (4.5:1) in both Appearances; `design/tokens.test.ts` checks
this against `tokens.css`, so a token change that breaks contrast fails the build.

### Where the accent goes

- The primary button of a view (Upload, Publish, Send, Save).
- The **current** crumb in the breadcrumb, and a crumb whose menu is open (soft fill).
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
- Menus and popovers: `rounded-2xl`, soft shadow (`surface.popover`).
- Page content: max width 1160px, 32px side padding (16px on phones), 28px between blocks.

## Layout

```
┌ TopBar ─────────────────────────────────────────────────────────────────────┐
│ ≈ Studio   Northwind Traders ▾ / Northwind Handbook ▾ / Documents ▾   ◐ (NN)│
└─────────────────────────────────────────────────────────────────────────────┘
   PageHeader: title + description                         [Edit details] [⋯]
   [StatCard] [StatCard] [StatCard] [StatCard]
   toolbar: (search) (All)(HR)(Products) Manage tags  [Any status ▾] [⤒ Upload]
   ┌ table.wrap ────────────────────────────────────────────────────────────┐
   │ ☐ Name                    Tags      Status   Chunks  Flagged  Size   ⋯ │
   └────────────────────────────────────────────────────────────────────────┘
```

### Navigation: the breadcrumb

The top bar's breadcrumb carries every level of navigation. Tab rows and the side menu go away.

| Where you are | Breadcrumb |
| --- | --- |
| Projects list | `Org ▾ / **Projects ▾**` |
| A Project section | `Org ▾ / Project ▾ / **Documents ▾**` |
| A Document | `Org ▾ / Project ▾ / Documents ▾ / **handbook.md**` |
| An Agent | `Org ▾ / Project ▾ / Agents ▾ / **HR helper ▾**` |
| Organisation settings | `Org ▾ / Settings ▾ / **Members ▾**` |
| Security, Profile | `Org ▾ / **Security**` (Profile and Sign out also live in the avatar menu) |

- Each crumb with siblings is a `CrumbSwitcher` that opens a menu of them: the Organisation
  switcher lists the Member's Organisations; the Project switcher lists Projects plus "All
  Projects"; a section switcher lists the sections with icons and number hints (1–6); an Agent
  switcher lists the Project's Agents.
- Ancestor crumbs are `muted`; the last crumb is the current page, in `accent`, with
  `aria-current="page"`. An open switcher turns soft green.
- A menu that navigates renders router `<Link>`s (`MenuItem.renderLink`) so items are real links.
- Sections a Member may not see (an Editor and Members or Audit) are left out of the menu, exactly
  as the tabs leave them out today.
- On narrow screens the breadcrumb wraps; if it must shorten, keep the Organisation and the
  current page and collapse the middle into "…".

### Pages

- **List and data pages** (Documents, Agents, Conversations, Members, Credentials, Audit):
  `PageHeader`, optional `StatCard` row, a toolbar, then a `table.wrap` card. Row actions in a ⋯
  `Menu` (`button.iconBare`), destructive items marked `danger`.
- **Agent page**: the Playground is the main column (max 720px, centred); configuration is a
  right-hand panel (360–420px) of collapsible `Section`s (Behaviour open; Retrieval, Experience,
  Guardrails collapsed with a mono summary). The trace folds open under each answer. Page actions
  (Saved state, History, Publish) sit in the top bar's right side.
- **Settings and forms**: a `surface.panel` per group, labels above fields, one primary button.
- **Signed-out pages** (sign in, sign up, reset, invite): a centred `surface.panel` on the canvas
  with the wave mark, no top bar.

## Components (`frontend/apps/studio/src/design`)

| Export | What |
| --- | --- |
| `tokens.css` | The tokens, the Appearance switch, base body styles and focus ring |
| `button`, `field`, `surface`, `table`, `text`, `notice`, `layout` | Class recipes |
| `TopBar`, `Brand`, `AppearanceToggle`, `Avatar` | The frame |
| `Breadcrumb`, `CrumbSwitcher`, `CrumbText`, `crumbClass()` | Navigation |
| `Menu`, `MenuItem`, `MenuLinkProps` | Switchers and ⋯ menus, keyboard-complete |
| `PageHeader`, `StatCard`, `Tag`, `Status`, `FlagCount`, `Notice`, `Section` | Content |
| `Icon`, `WaveMark` | Line icons (`documents`, `agents`, `more`, `upload`…) and the mark |
| `useAppearance`, `setAppearance`, `initAppearance` | Light / dark / system, remembered per browser |

## Appearance

The Member chooses light or dark with the toggle in the top bar; until they choose, the Studio
follows the system setting. The choice is stored in `localStorage` (`studio.appearance`) and
applied to `<html data-appearance>` before the first render by `initAppearance()`. It belongs to
the browser, not the Member's account.

## Don't

- Don't use raw colours, Tailwind palette classes, `dark:`, or inline `style` colours.
- Don't add tab rows or side navigation; add a crumb or a switcher item.
- Don't put more than one primary button in a view, or colour whole sections green.
- Don't use emoji or filled icons; use `Icon`.
- Don't restyle the widget preview (`ThemeScope`, `ChatWindow`): it shows the Organisation's Theme.
