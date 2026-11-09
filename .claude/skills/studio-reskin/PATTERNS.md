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

Also swap the markdown block's palette classes for tokens (`border-line`, `bg-sunken`), and give `code`
and `pre` `text-ink` so their text contrasts with the sunken fill on a page still on palette colours.

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
- **Org-level section crumb** (`menuLabel="Organisation sections"`): Projects, Cost (Owners only),
  Settings, Security, Profile. While MFA enrolment is required, offer only Security (today's
  `mustEnrol` rule). The page outside the menu (Cost for an Editor) gets a current `CrumbText`.
- **AccountMenu**: `Menu` with `label={<Avatar name={session.member.name} />}`,
  `triggerLabel={`${name}, Account`}`, `menuLabel="Account"`, `align="end"`,
  `triggerClassName="rounded-full"`; items Profile and Security (`renderLink`) and Sign out
  (`onSelect`, the existing `useSignOut` flow, keep its alert). Security was added in 11-12.
- **Page actions in the top bar** (the Agent's Saved / History / Publish): add a small portal
  slot (`TopBarActionsSlot` renders a `<div id="top-bar-actions">`; the page renders into it
  with `createPortal`), or a context holding a setter. Keep it to that one job. Built in 11-08:
  `shell/TopBarActions.tsx`. The Organisation shell renders the slot in the top bar and provides
  it; a page wraps its actions in `<TopBarActions>`.

Built in 11-04: `shell/StudioBreadcrumb.tsx`, `shell/OrganisationSwitcher.tsx` (`OrganisationCrumb`)
and `shell/AccountMenu.tsx`. A single-Organisation Member's crumb is plain text, not a link: a router
`<Link>` to the current page would claim `aria-current="page"`.

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

Confirmation steps that exist today become `ConfirmDialog`s.

Built in 11-05:

- `shell/StudioBreadcrumb.tsx` (`ProjectBreadcrumb`): inside a Project the breadcrumb is
  `Org / Projects ▾ / <Project> ▾ / <section> ▾`. The Organisation's section switcher stays as an
  ancestor. The Project switcher (`menuLabel="Projects"`) lists the open Projects, then All
  Projects. While the Project is loading or not found it is the current crumb and there is no
  section switcher. The Document viewer belongs to Documents; Agent and Conversation pages belong to
  their sections.
- `projects/ProjectPage.tsx`: `PageHeader` with Edit details and the ⋯ menu ("More Project
  actions", menu "Project actions"): Archive on an active Project; Delete permanently (Owners) on an
  archived one; no menu when it would be empty. Both confirm in a destructive `ConfirmDialog`;
  deletion types the name in the dialog's `body`. Restore stays in the archived notice.
- The Embedding Model is in the Settings section (`ProjectSettingsTab`), above OCR, and not shown
  for an archived Project (as before).
- Loading is `<Skeleton label="Loading the Project" />`; not found is `<EmptyState level={1}>`;
  a failed load is `<EmptyState tone="error">`.

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

Built in 11-06 (`projects/DocumentsTab.tsx`, `TagsPanel.tsx`, `DocumentViewer.tsx`):

- The stat row is a `section` named "Knowledge Base". Its figures are the whole Project's, whatever
  the filters show (a second, unfiltered `useDocuments`). The Embedding Model card prints the model id.
- The toolbar is `role="search"`: the search pill, Tag chips as a `Segmented` radio group "Filter by
  Tag" (All plus each Tag; hidden while there are none), Manage tags, then on the right Clear filters
  (while filtered), the status `select` ("Status", Any status) and Upload: a `button.primary`-shaped
  `<label>` around an `sr-only` file input named "Upload".
- The drop zone is `surface.dropzone`, text only; dragging over it turns it `accent-soft`.
- Columns: Select, Name, Type (`fileType()`: PDF, DOCX, PPTX, HTML, Markdown, Text, else File), Tags
  (`Tag` pills), Status (`Status` dot, then the failure category and message), Chunks, Flagged
  (`FlagCount`), Size, ⋯. The ⋯ button is "More actions for <name>", its menu "Actions for <name>":
  Retry and New edition (once Ready or Failed), Edit Tags, Delete. New edition clicks a `hidden`
  file input named "New edition of <name>". An archived Project has no ⋯, no selection, no Upload.
- Edit Tags is a `Dialog` "Tags for <name>" (checkboxes, Save Tags); Delete is a destructive
  `ConfirmDialog` "Delete <name>?" whose refusal shows in its `body`.
- Selection shows `BulkBar` with two `Menu`s, Add Tag and Remove Tag, listing the Tags. A `Menu`
  inside `BulkBar` keeps its own keys (the bar ignores keys a control already handled).
- Toasts (`ToastProvider` around the section): "Deleted <name>.", "Retrying <name>.", "Saved the Tags
  on <name>.", "Added <Tag> to 2 Documents.", "Removed <Tag> from 2 Documents.". Notices: upload
  refusals (error, in the Uploads list), a full quota (warning), failed Documents (warning), a
  refused retry (error).
- States: `Skeleton` "Loading Documents"; `EmptyState` for no Documents, no matches and a failed load.
- The Document viewer: the breadcrumb ends `… / Documents ▾ / <name>` (`DocumentCrumb`, "Document"
  until it loads, and the section switcher is then not the current crumb). The header has the
  name, a "Document details" list (status, type, size, chunks, flagged), Download original
  (`button.secondary`) and a warning `Notice` when Chunks are flagged. The markdown is in a
  `surface.panel`; each Chunk is a card (`rounded-2xl`, `border-flag` and `<Badge kind="flagged" />`
  when flagged); paging is `Pagination` "Chunk pages". The All Documents link is gone.

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
  (Built in 11-08 inside `layout.page`, as a wrapping two-column row; full bleed is left to 11-13.)

Built in 11-08:

- Routes: `/agents/$agentId` is the Agent page (`AgentPage`: header, archived notice, top bar
  actions) around its views: `/` Playground (`AgentPlaygroundView`), `/versions`
  (`AgentVersionsView`), `/embed` (`AgentEmbedView`). Conversations is a link to the Project's
  Conversations with `?agent=`; 11-10 shows it as a view in place.
- `shell/StudioBreadcrumb.tsx` (`AgentBreadcrumb`): `… / Agents ▾ / <Agent> ▾ / <view> ▾`. The
  Agent switcher (`menuLabel="Agents"`) lists the open Agents; the view switcher
  (`menuLabel="Agent views"`) is current. Until the Agent loads, or if it isn't found, the section
  switcher is current.
- Top bar: the Draft's save state (`role="status"`, "Draft status"), History (a link to Versions),
  Publish (`button.primary`, opens a `Dialog` holding the publish form). An archived Agent has no
  Publish.
- The ⋯ menu ("More Agent actions"): Discard Draft, Archive, Delete permanently, each a
  `ConfirmDialog`. Restore stays in the archived notice.
- Versions: Revert in "Actions for the Live Version", Start Draft from in "Actions for v<n>", each
  confirmed in a `ConfirmDialog`. Markdown changes in `AgentDiffView` are the design `Diff`.
- Visitor message: `self-end rounded-[18px] border border-line bg-surface px-4 py-3`.
- Answer: avatar circle `bg-accent-soft text-accent-ink`, text at 16px, citations
  `text-accent font-semibold` superscripts.
- Trace: `<details>` card (`surface.card`) whose summary is a mono row (model, tokens, latency,
  cost, guardrails); chunks listed inside, the cited one numbered in `text-accent`, flagged ones in
  `text-flag`. It replaces the drawer; keep the drawer's content and accessible names.
- Composer: a `rounded-full border border-line bg-surface` row with the input and `button.primary` Send.

## Round 2 patterns

All from `../design`. Tests find them by role and name, never by class.

```tsx
// Destructive confirmation: alertdialog, focus on Cancel, filled danger button, focus returns.
<ConfirmDialog
  open={confirming}
  title={`Delete ${doc.name}?`}
  confirmLabel="Delete"
  destructive
  busy={remove.isPending}
  onConfirm={() => { remove.mutate(); }}
  onCancel={() => { setConfirming(false); }}
>
  Its {doc.chunks} chunks are removed and Agents stop citing it.
</ConfirmDialog>

// A form in a dialog (Edit details): title, description, footer with the one primary button.
<Dialog open={editing} title="Edit details" onClose={close}
  footer={<><button className={button.secondary} onClick={close}>Cancel</button><button className={button.primary}>Save</button></>}>
  …fields…
</Dialog>

// After a reversible change. <ToastProvider> wraps the app once.
const toast = useToast();
toast.show(`Archived ${agent.name}.`, { onUndo: () => { restore.mutate(); } });

<Badge kind="live" />  <Badge kind="draft" />  <Badge kind="version" version={3} />
<Badge kind="lowSample" title="Fewer than 30 rated answers" />

<CodeBlock label="Embed snippet" code={snippet} />
<Meter label="Token Budget" value={used} max={budget} unit="tokens" />
<Diff label="System prompt, v2 to v3" before={a.system_prompt} after={b.system_prompt} />

{isPending ? <Skeleton label="Loading Documents" /> : documents.length === 0 ? (
  <EmptyState icon="documents" title="No Documents yet" description="Upload a file to start the Knowledge Base."
    action={<button className={button.primary}>Upload</button>} />
) : <table>…</table>}
{isError && <EmptyState tone="error" title="Couldn't load Documents" description="Try again in a moment." />}

<BulkBar count={selected.size} noun={["Agent", "Agents"]} onClear={clear}>
  <button className={button.secondary} onClick={publish}>Publish</button>
</BulkBar>
<Segmented label="Source" options={[{ value: "visitors", label: "Visitors" }, { value: "playground", label: "Playground" }]} value={source} onChange={setSource} />
<Pagination label="Conversations pages" page={page} pageCount={pages} onPageChange={setPage} />
<EditableList label="Allowed Origins" inputLabel="New origin" items={origins} onChange={setOrigins}
  validate={(v) => (/^https?:\/\//.test(v) ? undefined : "Start with https://")}
  emptyWarning="No site can embed this Agent until you add an origin." />
```

Old → new: a page's `confirm()` or inline "Are you sure?" panel → `ConfirmDialog`; a status
`<span>` with palette colours → `Badge`; a `<pre>` plus "Copy" button → `CodeBlock`; a progress
`<div>` → `Meter`; "Nothing here yet." text → `EmptyState`; "Loading…" text → `Skeleton`; a
`<select>` of two or three options shown as buttons → `Segmented`.

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
`menuLabel="Organisation settings"`). For "Editor can't see Members", expect
`sectionNames(page, "Organisation settings")` not to contain "Members".

Both helpers exist since 11-04, with the same names: `e2e/fixtures/navigation.ts` (Playwright, the
page first) and `apps/studio/src/test/navigation.ts` (Testing Library: `openSection`,
`sectionNames`, `currentSection`, `hasMenu`, `menuButton`). Menus that are still tab rows
are listed in each helper's `TAB_ROWS`; the slice that turns a row into a switcher deletes its
entry, and no test changes. "Organisation settings" is a switcher since 11-11
(`shell/SettingsCrumb.tsx`).
