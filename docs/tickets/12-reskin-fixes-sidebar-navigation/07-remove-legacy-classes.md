# 07: Remove the legacy BUTTON / INPUT strings

**Ticket:** `12-07` · **Spec:** [Reskin fixes and sidebar navigation](../../specs/12-reskin-fixes-sidebar-navigation-spec.md)

**What to build:** The last pages styled with the Projects page's old button and input strings (Agent branding among them) move onto the design system, and the old strings are deleted.

**Blocked by:**
- [12-03: Projects list reskin](03-projects-list-reskin.md)
- [12-04: Organisation cost reskin](04-organisation-cost-reskin.md)
- [12-06: Project Settings reskin and Embedding Model dialog](06-project-settings-reskin.md)

**Status:** done

- [x] Agent branding and any remaining importer use the design system's button and field recipes ([evidence](12-07-evidence/README.md#acceptance-criteria): `AgentBranding.tsx` on `button` / `field`; typecheck.log)
- [x] The Projects page no longer exports its BUTTON and INPUT strings, and nothing in the Studio defines its own button or input class string ([evidence](12-07-evidence/README.md#acceptance-criteria): `ProjectsPage.test.tsx`; `DraftEditor.tsx` alias removed; Theme page `SHORT` / `FIELD_ERROR` replaced by recipes; guard test `design/recipes.test.ts`)
- [x] Agent branding is checked in both Appearances, wide and narrow ([screenshots](12-07-evidence/screenshots/), [axe](12-07-evidence/shots-axe.log); the Theme page too)
- [x] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns, never Tailwind palette classes or `dark:`; the palette ratchet passes ([palette-ratchet.log](12-07-evidence/palette-ratchet.log))
- [x] Evidence: light and dark screenshots of the pages touched, wide (1440) and narrow (390), and the axe sweep in both Appearances ([screenshots](12-07-evidence/screenshots/), [shots-axe.log](12-07-evidence/shots-axe.log))
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds ([test.log](12-07-evidence/test.log))
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed (no new term, no decision changed; [evidence](12-07-evidence/README.md#acceptance-criteria))
