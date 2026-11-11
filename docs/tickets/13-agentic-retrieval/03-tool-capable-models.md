# 03: Models that support tools

**Ticket:** `13-03` · **Spec:** [Agentic retrieval](../../specs/13-agentic-retrieval-spec.md)

**What to build:** Editors can only run Agentic Agents on models that can use tools. The model picker shows which do, saving an Agentic Draft on one that can't is refused, and an Agent whose Default Model later loses tool support keeps answering.

**Blocked by:**
- [13-02: Agentic tracer: one Knowledge Search, end to end](02-agentic-tracer.md)

**Status:** done

- [x] Each capability-registry Model has a `supports_tools` flag, exposed in credential and model listings; the Demo models and the fake chat model support tools
- [x] Saving a Draft in Agentic mode is refused, with the field and reason, when the effective model (Model override, else the Default Model) lacks tool support
- [x] When an Agentic Agent's effective model lacks tool support at reply time (the Default Model changed), the reply runs as Automatic and the Trace carries a warning, shown in the Trace drawer
- [x] The Studio's model picker marks models that support tools
- [x] New Studio UI uses the design system ([docs/design/README.md](../../design/README.md), `frontend/apps/studio/src/design`): its tokens, recipes and shared patterns, never Tailwind palette classes or `dark:`; the palette ratchet passes
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed

Evidence: [13-03-evidence/README.md](13-03-evidence/README.md).
