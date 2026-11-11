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
| Agents | HR helper (scoped to HR), Product FAQ and Low-budget helper (scoped to Products) |
| Theme | Olive green and saffron, Lora |
| Default Model | The Demo model: canned answers quoted from the Knowledge Base, labelled as a demo. No API key needed. |

### The history

A fresh demo Organisation also gets four weeks of history (`backend/app/seed/history.py`, story in
`content.py`), played through the API under a clock set four weeks back:

| Days ago | What happens |
|---|---|
| 28 | The Organisation is set up; Instructions v1 ("House style"); Product FAQ, Low-budget helper and HR helper v1 published |
| 17 | The Editor publishes HR helper v2: one-sentence answers, no citations |
| 10 | The Owner reverts the HR helper to v1 |
| 6 | Instructions v2 ("No promises beyond policy"), bulk-published to the Low-budget helper; the Product FAQ stays behind on v1 |
| 3 | The Editor publishes HR helper v3: cites the handbook, points to HR contacts |

Every day until yesterday, Visitors chat with the HR helper (5 a day) and the Product FAQ (3 a
day) through the widget API, answered by the Demo model, and give thumbs and ratings drawn from a
fixed random seed: v2 is clearly worse than v1, and v3 looks better but is a small sample
("low confidence"). The usage rollup then runs for every day. It takes a few minutes; the history
is only made when the Organisation is created, so seeding again never repeats it.

To demo real answers, set `SEED_CREDENTIAL_PROVIDER` (`anthropic` or `openai`) and
`SEED_CREDENTIAL_API_KEY` before `make seed`; `SEED_CREDENTIAL_MODEL` picks the chat model
(default `claude-haiku-4-5` or `gpt-4.1-mini`). The seed adds that credential and makes it the
Default Model after the history (which always uses the Demo model); the demo credential stays. The stack must also run with `MODEL_GATEWAY=live` and
`CREDENTIAL_VERIFIER=live` for a real model to answer.

## Documents

- `documents/northwind-staff-handbook.md`: the staff handbook (HR). The end-to-end suite also
  uploads it. Its last section, "A note for AI assistants", is a planted indirect prompt
  injection: the ingestion Guardrail scan flags it, and the demo shows it.
- `documents/northwind-returns-policy.md`: the returns policy (Products). Its footnote is a
  planted indirect prompt injection for the Guardrails demo.
- `documents/northwind-product-faq.docx`: the product FAQ (Products).
- `documents/northwind-spring-range.pptx`: a slide deck (Products).

The Word document and the deck are made from `sources/*.md`; after changing a source, run
`uv run python -m tests.fixtures.make_seed_documents` in `backend/` and commit the outputs.
