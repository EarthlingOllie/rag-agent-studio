# Spec 12: Reskin fixes and sidebar navigation

**Status:** ready-for-agent · **Builds on:** [Spec 11](./11-studio-design-spec.md) (on `candidate-reskin`) · **Review:** [candidate-reskin design review](../reviews/candidate-reskin/README.md) · **Decision:** [draft ADR-0014](../reviews/candidate-reskin/0014-sidebar-navigation.md)

## Problem Statement

Spec 11 moved most of the Studio onto the Tidepool design system, but a design review of `candidate-reskin` found several gaps that make it feel unfinished and hard to move around in:

- **Three pages still have the old look.** The Organisation's Projects list, the Organisation cost page and a Project's Settings section use square bordered buttons, bare tables with underlined links, browser-default checkboxes and radios, and plain-text loading and empty messages. They sit right next to reskinned pages, so the difference is obvious.
- **Forms appear in the wrong place.**
  - *Create a Project:* the form is always shown, unstyled, under the Projects list.
  - *Edit details:* the form pushes an old-style form between the Project header and the page.
  - *Invite someone:* the form is a large panel between Members and Pending invites, which pushes the pending invites below the fold.

  The Agents list already solved this with a header button that opens a dialog.
- **Every dropdown looks cramped.** Each select keeps the browser's own arrow, which ignores the field's padding and sits against the right edge.
- **Navigation is hard to use.**
  - Every destination is hidden inside a breadcrumb menu, and a crumb is both "where you are" and a menu of somewhere else:
    - Cost and Settings are under the crumb labelled "Projects".
    - A Project's sections are under whichever section is open.
  - Security and Profile appear in two menus.
  - The Project section menu shows the numbers 1–6, which look like shortcuts but do nothing.
  - An Agent is six crumbs and five menus deep, under three stacked page headings.
  - On a phone, the top bar wraps into three rows, and the folded "…" hides exactly the crumbs a Member needs.

## Solution

Finish the reskin and replace the breadcrumb switchers with a sidebar.

- **Reskin the three remaining pages** like the Agents and Documents lists:
  - a page header with one primary action on the right;
  - a toolbar with a segmented filter;
  - a table card;
  - designed empty, loading and error states;
  - messages as notices or toasts.
- **Forms become dialogs** opened from a button in the header, right-aligned, as New Agent does:
  - New Project and Edit Project details share one Project details dialog.
  - Invite someone becomes a dialog. After an invite, the link to copy stays on the page.
  - Changing a Project's Embedding Model becomes a dialog too.
- **Every select gets the design system's own chevron**, inset to match the left padding, in both Appearances.
- **A contextual sidebar becomes the navigation** (ADR-0014, amending ADR-0013):
  - **Sidebar:** Organisation switcher; Projects, Cost (Owners) and Settings. Inside a Project, it also shows a Project switcher and the Project's six sections.
  - **Top bar:** the Studio mark, a plain breadcrumb of links that says where you are, the page's own actions, the Appearance toggle and the account menu.
  - **Account menu:** the only home of Profile, Security and Sign out.
  - **Agent pages:** the Agent's views are tabs under the Agent's header, and the page has a single h1.
  - **Phone:** the sidebar is a drawer.

## User Stories

### Projects list

1. As a Member, I want the Projects list to look like the rest of the Studio, so that the product feels finished and consistent.
2. As a Member, I want the Projects page to open with a clear title and a one-line description, so that I know what a Project is for.
3. As a Member, I want each Project's name, description, Document count and Agent count in a table card, so that I can compare Projects at a glance.
4. As a Member, I want a Project's name to be a link without underlines, styled like the Agents list, so that the table is easy to scan.
5. As a Member, I want long descriptions kept to one line in the list, so that rows stay the same height.
6. As a Member, I want numbers in the Documents and Agents columns right-aligned in mono, so that they line up.
7. As a Member, I want an Active / Archived filter above the table, so that I switch between them the same way as on Agents.
8. As a Member, I want archived Projects listed with the date they were archived, so that I can find the one I need.
9. As an Owner, I want to restore an archived Project from its row, so that I can bring it back without opening it.
10. As an Editor, I want to be told that only Owners can restore archived Projects, so that I know whom to ask.
11. As a Member, I want a designed empty state when there are no Projects (or no archived Projects), so that I know what to do next.
12. As a Member, I want a loading placeholder while Projects load, so that the page doesn't jump.
13. As a Member, I want a clear error state when Projects can't be loaded, so that I know to try again.
14. As an Owner, I want a success notice after a Project is deleted or restored, so that I know it worked.

### New Project and Edit details

15. As a Member, I want a New Project button at the top right of the Projects page, so that creating a Project is the obvious primary action.
16. As a Member, I want New Project to open a dialog with Name and Description, so that the form doesn't clutter the list.
17. As a Member, I want the dialog's fields styled like every other form, so that it feels part of the Studio.
18. As a Member, I want the new Project to open as soon as I create it, so that I can start adding Documents.
19. As a Member, I want to see why a Project couldn't be created inside the dialog, so that I can fix it without losing what I typed.
20. As a Member, I want Cancel and Escape to close the dialog without creating anything, with focus back on New Project, so that backing out is safe.
21. As a Member, I want New Project hidden while I'm looking at archived Projects, so that I'm not offered an action that doesn't fit that view.
22. As a Member, I want Edit details on a Project to open a dialog, so that the page doesn't shift under me.
23. As a Member, I want the Edit details dialog to show the current name and description, so that I only change what I need.
24. As a Member, I want a toast after saving details, with the header showing the new name, so that I know the change took.
25. As a Member, I want the Edit details button to stay where it is while I edit, so that the header doesn't rearrange.

### Organisation cost

26. As an Owner, I want the cost page to look like the other data pages, so that it's easy to read alongside them.
27. As an Owner, I want to switch between "by Project" and "by Agent" with a segmented control, so that the choice is one click.
28. As an Owner, I want From and To date filters styled like those on Conversations and Analytics, so that filtering works the same everywhere.
29. As an Owner, I want the period shown under the filters, so that I know exactly which days the figures cover.
30. As an Owner, I want amounts right-aligned in mono, with the total row set apart, so that I can compare spend quickly.
31. As an Owner, I want the total, Visitor and Playground spend shown as summary cards above the table, so that I see the headline before the detail.
32. As an Owner, I want a designed empty state when nothing was spent in the period, so that an empty table doesn't look broken.
33. As an Owner, I want an error notice that explains bad dates (From after To, or more than 366 days), so that I can correct them.
34. As an Editor, I want to be told that only Owners see the Organisation's spend, so that the empty page makes sense.
35. As an Owner on a phone, I want the cost table to scroll sideways inside its card, so that the page itself doesn't scroll sideways.

### Invite someone

36. As an Owner, I want an Invite someone button at the top right of Members, so that inviting is the obvious action and Pending invites stay in view.
37. As an Owner, I want Invite someone to open a dialog with Email, Role and "Email the invite link", so that the page stays a list of people.
38. As an Owner, I want the dialog to close and a toast to confirm the invite, so that I know it was sent.
39. As an Owner, I want the new invite's link and expiry shown on the page after the dialog closes, so that I can copy the link and send it myself.
40. As an Owner, I want an invalid email or an existing Member reported inside the dialog, so that I can correct it.
41. As an Owner, I want a new link from a pending invite to show the same copy-link panel, so that both paths behave the same.
42. As an Owner, I want the role select in each Member's row styled like other selects, so that the table looks consistent.

### Selects

43. As a Member, I want every dropdown's chevron inset from the right edge to match the text's left inset, so that fields look balanced.
44. As a Member, I want a long option's text never to run under the chevron, so that I can read the whole choice.
45. As a Member using the dark Appearance, I want the chevron to be visible against the dark field, so that I can tell it's a dropdown.
46. As a Member, I want a disabled select's chevron dimmed with the field, so that I can see it can't be changed.

### Project Settings

47. As a Member, I want a Project's Settings to look like Organisation settings, so that settings feel the same everywhere.
48. As a Member, I want Settings to open with a heading and a short description, so that I know what these settings control.
49. As a Member, I want each setting (Embedding Model, OCR, Flagged Chunks) in its own card with a title and explanation, so that I can scan and change one without reading them all.
50. As a Member, I want the current Embedding Model shown in mono with a Change button, so that I can see it and change it in one place.
51. As a Member, I want Change to open a dialog that warns me a change re-embeds every Document, so that I don't start a re-embed by accident.
52. As a Member, I want re-embed progress shown as a meter with Chunk counts, so that I know how long the old model will keep serving.
53. As a Member, I want a failed re-embed shown as an error notice with its reason, so that I can act on it.
54. As a Member, I want the OCR setting to be a clearly labelled toggle with its hint and current state, so that I understand the trade-off.
55. As a Member, I want the Flagged Chunk mode to be two clear choices with descriptions, so that I understand mark versus exclude.
56. As a Member, I want a setting to show my choice at once and be disabled while it saves, so that I don't double-submit.
57. As a Member on an archived Project, I want the settings shown but disabled, and no Embedding Model change offered, so that I can't change a Project that doesn't serve.

### Sidebar navigation

58. As a Member, I want every place I can go shown as a link in a sidebar, so that I don't have to guess which menu hides it.
59. As a Member, I want the link for the page I'm on highlighted, so that I always know where I am.
60. As a Member of several Organisations, I want an Organisation switcher at the top of the sidebar, so that I can change Organisation from anywhere.
61. As a Member of one Organisation, I want its name shown as plain text, so that I'm not offered an empty menu.
62. As an Owner, I want Projects, Cost and Settings as links in the sidebar, so that the Organisation's pages are one click away.
63. As an Editor, I want Cost left out of my sidebar, so that I'm not offered a page I can't use.
64. As a Member inside a Project, I want the Project's name with a switcher in the sidebar, so that I can jump to another Project or back to All Projects.
65. As a Member inside a Project, I want Documents, Instructions, Agents, Conversations, Analytics and Settings as links under the Project, so that every section is one click away.
66. As a Member on an Agent, a Document or a Conversation, I want its section (Agents, Documents, Conversations) to stay highlighted, so that I know which part of the Project I'm in.
67. As a Member, I want a plain breadcrumb in the top bar (for example "Northwind Handbook / Agents / HR helper"), whose crumbs are links, so that I can go back up a level in one click.
68. As a Member, I want Profile, Security and Sign out only in the account menu, so that each lives in one predictable place.
69. As a Member who must turn on MFA, I want the sidebar to offer only Security until I enrol, so that the Require MFA policy is clear.
70. As a Member, I want the page's own actions (Publish, History, the saved state) to stay in the top bar, so that I can still find them where they are today.
71. As a Member, I want no unexplained numbers beside links, so that nothing looks like a shortcut that doesn't work.

### Agent pages

72. As a Member on an Agent, I want Playground, Versions, Embed & limits and Conversations as tabs under the Agent's name, so that its views are visible and one click away.
73. As a Member on an Agent, I want to switch to another Agent from a ▾ on its name, so that I can move between Agents without going back to the list.
74. As a Member on an Agent, I want one page heading (the Agent's name) instead of the Project's, the Agent's and the view's stacked, so that the content starts higher.
75. As a Member on an Agent's Conversation, I want the Conversations tab to stay selected, so that I know where I am.

### Narrow screens and accessibility

76. As a Member on a phone, I want the sidebar to open as a drawer from a menu button, so that the content gets the full width.
77. As a Member on a phone, I want the drawer to close when I follow a link, press Escape or press outside it, so that it never gets in the way.
78. As a keyboard user, I want focus held inside the open drawer and returned to the menu button when it closes, so that I don't get lost.
79. As a keyboard user, I want the current link focused when the drawer opens, so that I start from where I am.
80. As a Member on a phone, I want the breadcrumb to show only its last two crumbs, so that the top bar fits on one row.
81. As a screen-reader user, I want the sidebar to be a named navigation landmark whose current link is announced as the current page, so that I can find it and know where I am.
82. As a screen-reader user, I want the Agent's views to be announced as tabs with the selected one marked, so that I understand the structure.
83. As a Member, I want every new dialog and the drawer to work in both Appearances and pass the accessibility checks, so that nothing regresses.

## Implementation Decisions

- **No backend or API changes.** Every story is served by endpoints and data that exist today. The generated API client is unchanged.
- **Behaviour is frozen except where named.** Permissions, routes and the data shown stay the same. The deliberate changes are:
  - Forms move into dialogs.
  - Cost's "Break down by" becomes a segmented control.
  - Navigation moves to the sidebar.
  - Agent views become tabs.
  - Profile and Security leave the Organisation's section list.
  - The Project header is no longer shown on Agent pages.
- **Projects page module.**
  - It stops exporting its local `BUTTON` and `INPUT` strings. Every other importer moves to the `button` and `field` recipes: the Embedding Model setting, Agent branding and Organisation cost.
  - Its `ProjectFields` uses `field.label`, `field.input` and `field.textarea`.
  - The Active / Archived switch is a `Segmented` control named "Projects shown", as on Agents.
  - Rows use the `table` recipes.
  - Restore is a row action for Owners and is confirmed by a toast.
- **Project details dialog.** One component serves create and edit (`mode: "create" | "edit"`). It uses the design system's `Dialog` without the corner close button, a form named "New Project" or "Project details", `FormError`, and a footer with Cancel and the primary action ("Create Project" / "Save", with "Creating…" / "Saving…" while pending). It replaces the inline New Project form and the inline Edit details form in the Project header.
- **Organisation cost module.**
  - Layout:
    - `PageHeader`.
    - A toolbar holding a `Segmented` control ("Break down by": Project / Agent) and two date filters using the `field.filter` and `field.pill` recipes.
    - A `StatCard` row: Total, Visitors, Playground.
    - The period line.
    - The table in `table.wrap`, using the numeric recipes for amounts and a distinguished total row.
  - Cost keeps its query shape (group by, from, to) and its 422 message.
  - The Audit page's own filter class string moves to the same filter recipes.
- **Members module.**
  - The Members header gets **Invite someone** as its primary action, which opens an invite `Dialog` with the existing fields and error mapping.
  - On success the dialog closes, the toast fires, and the existing copy-link panel renders on the page above Pending invites.
  - The row role select uses a new compact select recipe.
- **Select chevron.**
  - A base stylesheet rule for single-value selects:
    - removes the native arrow;
    - reserves right padding for the chevron, about 36 px;
    - draws a chevron from a new colour-aware token, positioned to mirror the field's left padding.
  - The token holds the design system's chevron-down icon, stroked in the muted colour. It has a light value and a dark value, declared in the same blocks as the other tokens (light, system-dark, chosen-dark).
  - Disabled selects dim the chevron.
  - The `field` recipes gain `selectCompact` for table cells. No page defines its own select class.
- **Project Settings module.**
  - Layout: `PageHeader level={2}`, then one `Section` card per setting.
  - Embedding Model:
    - Change opens a dialog with the model select and a warning `Notice` about re-embedding.
    - Progress uses `Meter` with "N of M Chunks".
    - Failure is an error `Notice`.
  - OCR is a labelled checkbox (or switch) row with its hint and status line.
  - The Flagged Chunk mode is a radio group of two described choices. It keeps `role="radiogroup"` and the existing optimistic, disabled-while-saving behaviour.
  - An archived Project shows the settings disabled and hides Embedding Model.
- **Navigation (ADR-0014).**
  - **Organisation shell:** it gains a `Sidebar` beside the main content.
    - The sidebar is a navigation landmark named "Studio".
    - It is computed from the route and the Member's session, not registered by pages, just as the breadcrumb is computed today.
    - Its contents:
      - The Organisation switcher, which reuses the existing switcher's menu.
      - The Organisation's links: Projects, Cost (Owners), Settings.
      - Inside a Project: the Project switcher (open Projects, then All Projects) and the six section links.
    - The current link uses the soft accent fill and `aria-current="page"`.
    - A section stays current on its inner pages: the Document viewer under Documents, an Agent under Agents, a Conversation under Conversations.
    - Under the Require MFA policy, the sidebar offers only Security.
  - **Breadcrumb:** it becomes plain links with no switcher menus.
    - The `CrumbSwitcher` usage goes away from the shell.
    - Below `md` the breadcrumb shows only the last two crumbs, so the fold popover goes away.
  - **Account menu:** keeps Profile, Security and Sign out. The Organisation's section list no longer includes Security or Profile.
  - **Drawer:** below `md` the sidebar is a drawer behind a menu button named "Open navigation", with:
    - focus trapped inside it;
    - Escape, a press outside, or following a link closes it;
    - focus returned to the button on close;
    - the current link focused on open.

    It may reuse the `Dialog` focus-trap behaviour.
  - **Menu hints:** the numeric hints on Project sections are dropped.
  - **Content width:** the main content keeps its 1160 px maximum, centred in the space beside the sidebar. The sidebar is about 240 px wide and fixed.
- **Agent page module.**
  - The Agent's views render as a tab row (links styled as tabs, with `aria-current`) under the Agent's `PageHeader`.
  - The Agent switcher is a ▾ menu on the Agent's title.
  - The Project layout skips the Project `PageHeader` on Agent routes, so the Agent's name is the page's h1.
- **Docs.**
  - The draft ADR-0014 moves into the ADR folder.
  - The design README changes in three places: principle 3, the navigation table and the breadcrumb section, which is replaced by a sidebar section.
  - GLOSSARY:
    - Breadcrumb now means a plain path of links.
    - Breadcrumb fold and Crumb switcher are removed.
    - Sidebar and Sidebar drawer are added.

## Testing Decisions

- **Good tests** assert what a Member sees and does, by role and accessible name. For example: "the New Project dialog opens; after submit the Project's page is shown"; "the sidebar's Cost link is absent for an Editor"; "the Agents link has `aria-current=page` on an Agent". They never assert class names or colours. The one exception is the token contract test, which reads the stylesheet by design.
- **Seams** (no new ones):
  - **Network seam (main).** Testing Library with MSW handlers typed by the generated client, rendering routes through the existing Studio test renderer. It covers:
    - the reskinned pages' states (loading, empty, error, success notices);
    - the Project details dialog in both modes;
    - the invite dialog and the copy-link panel after it;
    - Cost's segmented control and date filters, including the 422 message;
    - Project Settings behaviour (optimistic, disabled, archived);
    - the sidebar's links, role and MFA hiding, and current link;
    - the plain breadcrumb;
    - the account menu's contents;
    - Agent view tabs and the Agent switcher;
    - the drawer's keyboard path (open, focus current, trap, Escape, outside press, link follow, focus return).
  - **End-to-end seam.** Playwright against the compose stack, with the axe sweep in both Appearances. It covers:
    - the navigation journeys;
    - the drawer at phone width;
    - layout facts only a real browser shows: a select's computed `appearance` is `none`, its right padding is at least 36 px, and the page has no horizontal scroll at 390 px.

    The accessibility sweep's page list gains the dialogs and the open drawer.
  - **Token contract test (exists).** It gains checks that the chevron token is declared in the light, system-dark and chosen-dark blocks, and that the latter two match.
- **Navigation helpers.**
  - The shared Playwright helper and its Testing Library twin are rewritten in place, from opening a crumb menu to clicking a sidebar or account-menu link.
  - Their names (`openSection`, `sectionNames`) and the menu vocabulary they take stay the same where possible, so the ~50 existing end-to-end specs change little:
    - "Organisation sections" and "Project sections" read the sidebar's link groups.
    - "Agent views" reads the tab row.
    - "Account" stays a menu.
  - Role-based hiding stays asserted as "the list has no such item".
  - This rewrite lands first in the navigation ticket, before the crumb switchers are removed.
- **Existing specs to move:**
  - `projects`, `project-deletion`, `organisation-cost`, `members`, `invites` and `embedding-models`, to the dialogs and new controls;
  - `organisation-switcher` and `require-mfa`, to the sidebar;
  - the 11-13 keyboard pass, to the sidebar, drawer and tabs.
- **Coverage** stays at 100% line and branch (ADR-0008). The palette ratchet stays at none allowed.
- **Prior art:**
  - `AgentsTab` and its tests: the header primary action that opens a dialog, the `Segmented` filter, table states.
  - The Organisation settings reskin (11-11): section cards.
  - The Dialog and Menu tests: keyboard paths.
  - The shell tests: the computed breadcrumb.
  - The 11-13 evidence scripts: wide and narrow screenshots, axe and the keyboard pass.

## Out of Scope

- Any backend, API or data model change.
- New features on these pages, such as sorting, searching or paginating Projects, or exporting cost.
- A command palette, and real keyboard shortcuts for sections (the old 1–6 hints are removed, not wired up).
- A collapsible or resizable desktop sidebar, and remembering its state.
- Reskinning pages not named here beyond moving them onto shared classes. The exception is Agent branding, which must stop importing the removed strings.
- The widget, the Organisation Theme and the Theme editor's preview.
- Visual regression (pixel-diff) tooling.

## Further Notes

- **Evidence.** Screenshots of every finding, taken with Playwright against the seeded stack at `candidate-reskin` 8cd1483, are in [docs/reviews/candidate-reskin](../reviews/candidate-reskin/README.md).
- **Tickets:** [`docs/tickets/12-reskin-fixes-sidebar-navigation/`](../tickets/README.md#12-reskin-fixes-and-sidebar-navigation): eleven tickets, 12-01 to 12-11. 12-01, 12-02, 12-04, 12-05, 12-06 and 12-08 can start at once.
- **Order of work in 12-08 to 12-11.** 12-08 rewrites the helpers and adds the sidebar while the crumb switchers still exist; 12-11 removes them last. That keeps every end-to-end spec green throughout, as spec 11's navigation slice did.
- **Base branch.** This spec targets `candidate-reskin`. Its links to spec 11 and the design README resolve there.
