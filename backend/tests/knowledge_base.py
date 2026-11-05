"""The fixture Knowledge Base for retrieval tests: Chunks whose relevance to each query is known.

It is uploaded through the API and ingested eagerly with the fake converter and the
deterministic embedder. Each file is one Chunk with no headings, so a Chunk's embedded text is
the file's text. The embedder hashes a query like a passage: a query equal to a Chunk's text
finds that Chunk with a semantic score of 1, and every other text scores close to 0. So:

- semantic search finds a Chunk only when asked its exact text;
- keyword (full-text) search finds Chunks sharing words with the query, which is the only way
  to find ``PRODUCT`` by its product code;
- ``RULES`` and ``RULES_REPEATED`` disagree: semantic search ranks ``RULES`` first for the
  query ``RULES``, keyword search ranks ``RULES_REPEATED`` first (it repeats every query term),
  so the hybrid weighting decides which comes first.
"""

from fastapi import FastAPI

from tests.conftest import SignedUpMember
from tests.documents import create_project, upload

LEAVE = "Everyone gets 25 days of annual leave a year."
EXPENSES = "Claim expenses within 30 days of spending."
PARKING = "Visitors park in the north car park."
PRODUCT = "Model SKU-4471 ships with a two-year warranty."
RULES = "Overtime rules."
RULES_REPEATED = "Overtime rules: overtime rules apply, and overtime rules are strict."

FILES = {
    "leave.txt": LEAVE,
    "expenses.txt": EXPENSES,
    "parking.txt": PARKING,
    "product.txt": PRODUCT,
    "rules.txt": RULES,
    "rules-repeated.txt": RULES_REPEATED,
}

# Asks about the product by its code: no Chunk has this text, so semantic search can't tell
# which Chunk is relevant. Postgres parses it into six terms (what, warranty, does, sku, -4471,
# have); three of them (warranty, sku, -4471) are in PRODUCT.
PRODUCT_QUESTION = "What warranty does SKU-4471 have?"
# Shares only "the" with PARKING and nothing with the rest: nothing relevant is known.
UNRELATED_QUESTION = "What is the canteen menu?"


async def knowledge_base(app: FastAPI, member: SignedUpMember, name: str = "Handbook") -> str:
    """Creates a Project holding the fixture Knowledge Base; returns its ID."""
    project_id = await create_project(member, name)
    for filename, text in FILES.items():
        await upload(app, member, project_id, filename, text.encode())
    return project_id
