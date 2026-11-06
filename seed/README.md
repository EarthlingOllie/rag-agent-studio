# Seed content

Synthetic, freely licensed content for the demo Organisation (spec 10) and for local
development. See [LICENCE.md](LICENCE.md): everything here is CC0 and about Northwind Traders, a
fictional company.

## The demo Organisation

With the stack running (`make dev`), `make seed` creates it through the platform's own API and
prints the sign-in details. Running it again changes nothing; `make seed-reset` erases the demo
Organisation (and only that one) and seeds it again.

| What | Value |
|---|---|
| Organisation | Northwind Traders |
| Owner | `owner@northwind.example`, password `northwind-owner-demo` |
| Editor | `editor@northwind.example`, password `northwind-editor-demo` |
| Project | Northwind Handbook, Tags HR and Products |
| Agents | HR helper (scoped to HR), Product FAQ (scoped to Products) |
| Theme | Olive green and saffron, Lora |
| Default Model | The Demo model: canned answers quoted from the Knowledge Base, labelled as a demo. No API key needed. |

To demo real answers, set `SEED_CREDENTIAL_PROVIDER` (`anthropic` or `openai`) and
`SEED_CREDENTIAL_API_KEY` before `make seed`; `SEED_CREDENTIAL_MODEL` picks the chat model
(default `claude-haiku-4-5` or `gpt-4.1-mini`). The seed adds that credential and makes it the
Default Model; the demo credential stays. The stack must also run with `MODEL_GATEWAY=live` and
`CREDENTIAL_VERIFIER=live` for a real model to answer.

## Documents

- `documents/northwind-staff-handbook.md`: the staff handbook (HR). The end-to-end suite also
  uploads it.
- `documents/northwind-returns-policy.md`: the returns policy (Products). Its footnote is a
  planted indirect prompt injection for the Guardrails demo.
- `documents/northwind-product-faq.docx`: the product FAQ (Products).
- `documents/northwind-spring-range.pptx`: a slide deck (Products).

The Word document and the deck are made from `sources/*.md`; after changing a source, run
`uv run python -m tests.fixtures.make_seed_documents` in `backend/` and commit the outputs.
