# Studio reskin patterns

Code for each slice in [SKILL.md](SKILL.md). Paths are relative to `frontend/apps/studio/`.
Adapt names to the code as you find it; other agents keep changing these pages.

## Class mapping

| Old | New |
| --- | --- |
| `bg-slate-50` (page) | nothing: `body` is `bg-canvas` via tokens.css |
| `bg-white` (card/header) | `bg-surface` (or `surface.card` / `surface.panel`) |
| `text-slate-900` | `text-ink` |
| `text-slate-700`, `text-slate-600` | `text-muted` (descriptions, meta) or `text-ink-2` (labels) |
| `border-slate-200` | `border-line`; row dividers `border-line-soft` |
| `border-slate-300`, `border-slate-400` (controls) | `border-field` |
| `hover:bg-slate-100` | `hover:bg-sunken` |
| `bg-slate-900 … text-white` (primary) | `button.primary` |
| `border … px-3 py-1 text-sm` (secondary) | `button.secondary` (or `button.ghost` in toolbars) |
| `bg-red-700 text-white` (destructive confirm) | `button.danger`, or a `danger` menu item |
| `text-red-700/800` | `text-danger` (`field.error` under inputs) |
| `border-red-200 bg-red-50 text-red-800` (`FormError`) | `notice.error` / `<Notice tone="error">` |
| `bg-green-50 text-green-900` | `notice.success` / `<Notice tone="success">` |
| `bg-amber-50 text-amber-900` | `notice.warning` / `<Notice tone="warning">` |
| `rounded … px-3 py-2` inputs (`INPUT`) | `field.input`, `field.select`, `field.textarea`, `field.inputMono` |
| `underline` links | `text.link` (running text) or `table.link` (name cells) |
| `font-mono` numbers | keep `font-mono`; size 13px in tables (`table.tdNumeric`) |
| `text-2xl font-semibold` page `h1` | `PageHeader` (`text.title`) |
| `text-lg font-semibold` section `h2` | `text.heading` |
| `TAB` link rows | a `CrumbSwitcher` (see R2) |

## R0: Foundation

`src/index.css`, right after `@import "tailwindcss";`:

```css
@import "./design/tokens.css";
```

Also swap the markdown block's palette classes for tokens (`border-line`, `bg-sunken`).

`index.html` `<head>`:

```html
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet" />
```

`src/main.tsx`, before `createRoot`:

```ts
import { initAppearance } from "./design";
initAppearance();
```

## R1: Shell

`OrganisationShell` renders the `TopBar`; the breadcrumb is computed from the route, so pages
don't have to register anything. Split by depth so each part calls its hooks unconditionally:

```tsx
import { Link, useMatchRoute, useParams } from "@tanstack/react-router";
import { AppearanceToggle, Avatar, Breadcrumb, Brand, button, CrumbSwitcher, Icon, layout, Menu, TopBar } from "../design";

<div className="min-h-screen">
  <TopBar
    home={<Link to="/" aria-label="Studio home"><Brand /></Link>}
    breadcrumb={<StudioBreadcrumb session={session} organisationId={organisationId} />}
    actions={<><TopBarActionsSlot /><AppearanceToggle /><AccountMenu session={session} organisationId={organisationId} /></>}
  />
  <main className={layout.page}>{/* the Navigate-or-Outlet logic that is there today */}</main>
</div>
```

- **Organisation crumb**: `CrumbSwitcher menuLabel="Organisations"`, items from
  `session.organisations`, `onSelect` calls the existing `useSwitchOrganisation` mutation then
  navigates, exactly as `OrganisationSwitcher` does today (keep its error alert). With one
  Organisation, render it as a link to its Projects (`<Link className={crumbClass()}>`).
- **Org-level section crumb** (`menuLabel="Organisation"`): Projects, Settings, Security. While
  MFA enrolment is required, offer only Security (today's `mustEnrol` rule).
- **AccountMenu**: `Menu` with `label={<Avatar name={session.member.name} />}`,
  `triggerLabel="Account"`, `align="end"`, `triggerClassName="rounded-full"`; items Profile and
  Security (`renderLink`) and Sign out (`onSelect`, the existing `useSignOut` flow, keep its alert).
- **Page actions in the top bar** (the Agent's Saved / History / Publish): add a small portal
  slot (`TopBarActionsSlot` renders a `<div id="top-bar-actions">`; the page renders into it
  with `createPortal`), or a context holding a setter. Keep it to that one job.

A navigating switcher item:

```tsx
{
  label: "Agents",
  icon: "agents",
  hint: "3",
  current: matchRoute({ to: `${PROJECT}/agents`, fuzzy: true }) !== false,
  renderLink: (props) => <Link to={`${PROJECT}/agents`} params={{ organisationId, projectId }} {...props} />,
}
```

## R2: Project frame

```tsx
function ProjectCrumbs({ organisationId, projectId }: { organisationId: string; projectId: string }) {
  const projects = useProjects(organisationId, false);
  const project = useProject(organisationId, projectId);
  const matchRoute = useMatchRoute();
  const sections = SECTIONS.map((section, index) => ({
    label: section.label,
    icon: section.icon,
    hint: String(index + 1),
    current: matchRoute({ to: section.to, params: { organisationId, projectId }, fuzzy: section.fuzzy }) !== false,
    renderLink: (props: MenuLinkProps) => <Link to={section.to} params={{ organisationId, projectId }} {...props} />,
  }));
  const here = sections.find((section) => section.current) ?? sections[0];
  // Last crumb is current only when no deeper crumb (Document, Agent) follows.
  return (
    <>
      <CrumbSwitcher label={project.data?.name ?? "Project"} menuLabel="Projects" items={[/* projects + "All Projects" */]} />
      <CrumbSwitcher label={here.label} menuLabel="Project sections" current={!deeper} items={sections} />
    </>
  );
}
```

`SECTIONS` replaces `TABS` in `ProjectPage.tsx` (Documents `documents`, Instructions
`instructions`, Agents `agents`, Conversations `conversations`, Analytics `analytics`, Settings
`settings` icons). Documents is the index route, so match it exactly (no `fuzzy`) and add the
Document viewer route to it.

The Project page body becomes:

```tsx
<PageHeader
  title={project.name}
  description={project.description}
  actions={<>
    <button type="button" className={button.secondary} onClick={startEditing}>Edit details</button>
    <Menu label={<Icon name="more" />} triggerLabel="More Project actions" align="end" triggerClassName={button.icon}
      items={[{ label: "Archive", onSelect: confirmArchive }, { label: "Delete permanently", danger: true, onSelect: confirmDelete }]} />
  </>}
/>
```

Confirmation steps that exist today stay; they render below the header as a `surface.panel`.

## R3: Documents

```tsx
<div className={layout.stats}>
  <StatCard label="Documents" value={count} unit={`/ ${quota}`} />
  <StatCard label="Chunks" value={chunks} />
  <StatCard label="Flagged chunks" value={flagged} tone={flagged > 0 ? "flag" : "default"} />
  <StatCard label="Embedding model" value={<span className="text-[15px]">{model}</span>} />
</div>

<div className={layout.toolbar}>
  <label className={`${field.search} flex-1 basis-60`}>
    <Icon name="search" />
    <input type="search" aria-label="Search by name" className="flex-1 bg-transparent text-ink outline-none" />
  </label>
  {/* Tag chips: aria-pressed buttons; selected = "bg-ink text-surface", others = button.ghost */}
  <button type="button" className={button.primary}><Icon name="upload" />Upload</button>
</div>

<div className={table.wrap}>
  <table className={`${table.table} min-w-[760px]`}>
    {/* th: table.th / table.thNumeric; rows: table.row; cells: table.td / table.tdNumeric */}
    <td className={table.td}><Tag>Products</Tag></td>
    <td className={table.td}><Status tone="ready">Ready</Status></td>
    <td className={table.tdNumeric}><FlagCount count={doc.flagged} label="flagged chunks" /></td>
    <td className={table.td}>
      <Menu label={<Icon name="more" />} triggerLabel={`Actions for ${doc.name}`} align="end" triggerClassName={button.iconBare}
        items={[{ label: "Edit Tags", onSelect }, { label: "Retry", onSelect }, { label: "New edition", onSelect }, { label: "Delete", danger: true, onSelect }]} />
    </td>
  </table>
</div>
```

Status tones: Ready `ready`, Queued/Processing `working`, Failed `failed`.
The Tags panel opens from "Manage tags" (a `button.ghost` in the toolbar) as a `surface.panel`.

## R4: Agent + Playground

```tsx
<div className="flex min-h-[calc(100vh-65px)] flex-wrap">
  <section aria-label="Playground" className="flex min-w-0 flex-[999_1_560px] flex-col px-4 py-10 sm:px-8">
    <div className="mx-auto flex w-full max-w-[720px] flex-1 flex-col gap-7">{/* messages, composer */}</div>
  </section>
  <aside aria-label="Draft" className="flex-[1_1_360px] border-l border-line bg-surface lg:max-w-[420px]">
    <Section title="Behaviour" defaultOpen>…</Section>
    <Section title="Retrieval" summary={`top-${k} · hybrid ${w}`}>…</Section>
    <Section title="Experience">…</Section>
    <Section title="Guardrails" summary={mode}>…</Section>
  </aside>
</div>
```

- The Agent page drops `layout.page` padding (full-bleed two-column layout); everything else keeps it.
- Visitor message: `self-end rounded-[18px] border border-line bg-surface px-4 py-3`.
- Answer: avatar circle `bg-accent-soft text-accent-ink`, text at 16px, citations
  `text-accent font-semibold` superscripts.
- Trace: `<details>` card (`surface.card`) whose summary is a mono row (model, tokens, latency,
  cost, guardrails); chunks listed inside, the cited one numbered in `text-accent`, flagged ones in
  `text-flag`. It replaces the drawer; keep the drawer's content and accessible names.
- Composer: a `rounded-full border border-line bg-surface` row with the input and `button.primary` Send.

## Tests: a navigation helper for Playwright

`e2e/fixtures/navigation.ts`:

```ts
import type { Page } from "@playwright/test";

/** Opens a breadcrumb switcher ("Project sections", "Organisation", "Projects"…) and follows an item. */
export async function openSection(page: Page, menu: string, item: string) {
  const breadcrumb = page.getByRole("navigation", { name: "Breadcrumb" });
  await breadcrumb.getByRole("button", { name: new RegExp(`, ${menu}$`) }).click();
  await page.getByRole("menu", { name: menu }).getByRole("menuitem", { name: item }).click();
}
```

Replace `getByRole("navigation", { name: "Project" }).getByRole("link", { name: "Agents" }).click()`
with `openSection(page, "Project sections", "Agents")`, and the settings tabs with
`openSection(page, "Organisation settings", "Members")` (give the Settings switcher
`menuLabel="Organisation settings"`). For "Editor can't see Members", open the menu and expect
`getByRole("menuitem", { name: "Members" })` to have count 0.
