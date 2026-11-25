# 02: ElevenLabs Provider Credential

**Ticket:** `20-02` · **Spec:** [Calls](../../specs/20-calls-spec.md)

**What to build:** An Owner adds an ElevenLabs Provider Credential in Organisation settings › Credentials; it is checked live, encrypted and offers the new voice Capability.

**Blocked by:**
- None

**Status:** ready-for-agent

- [ ] The capability registry gains the provider ElevenLabs (API key auth) and the Capability `voice`; `GET /api/providers` lists them and existing providers are unchanged
- [ ] The Credential check for ElevenLabs proves the key works and can use the agents API, failing with the existing typed reasons (invalid key, quota exceeded, provider unreachable); the fake verifier covers it
- [ ] The key is envelope-encrypted, shown only as its Key hint, and can be rotated and re-checked like any other credential
- [ ] A voice credential is never offered in a chat, embedding or reranker picker
- [ ] Credentials shows ElevenLabs in the provider list with its voice Capability
- [ ] Adding, rotating and deleting it are Audit Events; Editors can't manage it; another Organisation's credential is unreachable
- [ ] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns (dialogs, toasts, badges, code blocks, meters, diffs, empty and loading states, bulk bar, segmented control, pagination, editable list), never Tailwind palette classes or `dark:`; the palette ratchet passes
- [ ] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [ ] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
