# 12: Signed-out pages, profile, security and status

**Ticket:** `11-12` · **Spec:** [Studio design system and reskin](../../specs/11-studio-design-spec.md)

**What to build:** Sign up, sign in, MFA, password reset, invites, profile, security and the status page follow the system, and loading, empty and error states read the same everywhere.

**Blocked by:**
- [11-04: Shell, breadcrumb and navigation test helpers](04-shell-navigation.md)

**Status:** done

- [x] Signed-out pages are a centred panel with the wave mark and no top bar; `FormError` becomes `Notice`
- [x] Profile and Security are reachable from the account menu and the breadcrumb; MFA enrolment shows the QR code and recovery codes on cards
- [x] The status page uses `Status` dots for each dependency
- [x] Shell loading and error states use `Skeleton` and `Notice`
- [x] Behaviour is unchanged apart from what this ticket names; moved actions are listed in the PR
- [x] The palette ratchet baseline is lowered to the new count
- [x] Light and dark screenshots of every page changed are in the ticket's evidence folder, matching the mockups on the design canvas
- [x] axe reports zero AA violations on the changed pages in both Appearances
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed

Evidence: [11-12-evidence/README.md](11-12-evidence/README.md).
