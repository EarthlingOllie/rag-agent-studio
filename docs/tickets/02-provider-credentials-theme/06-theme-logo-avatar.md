# 06: Theme logo and avatar

**Ticket:** `02-06` · **Spec:** [Provider Credentials and Theme](../../specs/02-provider-credentials-theme-spec.md)

**What to build:** Owners upload a logo and a default Agent avatar for the Theme, and see them in the preview.

**Blocked by:**
- [02-05: Theme editor](05-theme-editor.md)
- [03-02: Upload a Document to Ready](../03-projects-knowledge-base/02-upload-document-to-ready.md)

**Status:** done

- [x] Logo and avatar are uploaded through presigned uploads via the object-store port, restricted by image type and size
- [x] Images show in the Theme preview
- [x] Images can be replaced and removed, and changes are audited
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
