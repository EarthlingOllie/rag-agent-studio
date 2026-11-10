# 05: Invite dialog

**Ticket:** `12-05` · **Spec:** [Reskin fixes and sidebar navigation](../../specs/12-reskin-fixes-sidebar-navigation-spec.md)

**What to build:** An Owner invites someone from a dialog opened by Invite someone at the top right of Members, so Members and Pending invites stay in view.

**Blocked by:**
- None

**Status:** done

- [x] The Members section has a header with Invite someone as its primary action, top right; the inline invite panel is gone
- [x] Invite someone opens a dialog with Email, Role and "Email the invite link"; an invalid email or an existing Member is reported inside it
- [x] On success the dialog closes, the toast confirms the invite, and the panel to copy the Invite Link (with its expiry) shows on the page above Pending invites
- [x] New link on a pending invite shows the same copy-link panel
- [x] Cancel and Escape close the dialog without inviting, and focus returns to Invite someone
- [x] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns, never Tailwind palette classes or `dark:`; the palette ratchet passes
- [x] Evidence: light and dark screenshots of the pages touched, wide (1440) and narrow (390), and the axe sweep in both Appearances
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
