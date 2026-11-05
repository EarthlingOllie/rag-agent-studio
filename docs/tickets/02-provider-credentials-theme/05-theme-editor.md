# 05: Theme editor

**Ticket:** `02-05` · **Spec:** [Provider Credentials and Theme](../../specs/02-provider-credentials-theme-spec.md)

**What to build:** Owners style the Organisation's Theme (colours, radius, font, mode, launcher) and see a live preview of the widget, with a warning if any colour pair fails accessible contrast.

**Blocked by:**
- [01-09: Member management and role enforcement](../01-skeleton-auth-tenancy/09-member-management-roles.md)

**Status:** done

- [x] The Theme stores colour tokens with dark-mode values, radius, a font from the allowlist, mode, launcher type and launcher position
- [x] A pure resolution function produces CSS custom properties, shared by the Studio preview and the widget
- [x] The live preview renders the shared UI primitives
- [x] Pairs that fail WCAG AA contrast produce a warning, not a block
- [x] Owners edit and Editors view; changes are audited
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
