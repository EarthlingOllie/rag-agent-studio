# 02: Markdown editor

**Ticket:** `04-02` · **Spec:** [Agents, retrieval and Playground](../../specs/04-agents-retrieval-playground-spec.md)

**What to build:** Every prompt field becomes a lightweight markdown WYSIWYG editor that stores markdown exactly. It's used for the Agent system prompt and for a Project-wide Instructions field that the runtime passes to every Agent.

**Blocked by:**
- [04-01: Agent and Playground tracer](01-agent-playground-tracer.md)

**Status:** done

- [x] A TipTap-based editor in the shared UI package stores markdown
- [x] A fixture table of headings, lists, code, links and emphasis round-trips exactly
- [x] The editor is used for the Agent system prompt and the Project Instructions (one Draft field per Project, passed to the runtime)
- [x] Instructions edits are recorded as Audit Events
- [x] Tests cover the new behaviour at the highest seam (see [shared test seams](../../specs/README.md#shared-test-seams)); 100% line and branch coverage holds
- [x] New domain terms are added to `GLOSSARY.md`; ADRs updated if a decision changed
