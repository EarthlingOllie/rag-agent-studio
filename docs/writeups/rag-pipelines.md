# RAG pipelines

*How RAG Agent Studio turns uploaded files into grounded, cited, measurable answers.*

> **Status:** this describes the design as specified in this repository ([plan §2](../plan.md#2-architecture), [spec 03](../specs/03-projects-knowledge-base-spec.md), [spec 04](../specs/04-agents-retrieval-playground-spec.md), [spec 07](../specs/07-feedback-logging-comparison-spec.md) and ADRs [0001](../adr/0001-pgvector-hybrid-search.md), [0002](../adr/0002-local-embeddings-by-default.md) and [0003](../adr/0003-immutable-versions-with-live-pointer.md)). Implementation has not started yet, so nothing below is a measured production result.

---

## 1. What the pipeline has to do

Retrieval-augmented generation (RAG) is really two pipelines that share one datastore:

- an **ingestion pipeline** that runs in the background and turns messy files into clean, searchable Chunks;
- a **query pipeline** that runs on every message, finds the right Chunks and gets the model to answer from them, with citations.

RAG Agent Studio adds three production requirements on top:

1. **Isolation.** Each Project is a separate Knowledge Base. An HR Agent must never retrieve sales material, and no data crosses an Organisation.
2. **Visibility.** Editors must be able to see what was extracted, what was retrieved, what was filtered out and why, for every single answer.
3. **Change without downtime.** Documents get replaced, Embedding Models change and Agents get republished, all while Visitors are chatting.

```
                 INGESTION (Celery worker)                         QUERY (FastAPI, per message)
 ┌─────────┐   ┌─────────┐   ┌───────┐   ┌───────────────┐        ┌──────────────┐
 │ Upload  │──▶│ Convert │──▶│ Chunk │──▶│ Embed + scan  │──┐     │ Visitor msg  │
 │ (S3 PUT)│   │ Docling │   │Hybrid-│   │ local / provider│ │     └──────┬───────┘
 └─────────┘   └─────────┘   │Chunker│   └───────────────┘  │            ▼
                             └───────┘                      │     embed query (same model)
                                                            ▼            ▼
                                ┌────────────────────────────────────────────────┐
                                │ Postgres 16: chunks (text, vector, tsvector,    │
                                │ project_id, embedding model, guardrail flags)   │
                                └────────────────────────────────────────────────┘
                                                            ▲            │
                                                            │   vector ∥ full-text
                                                            │            ▼
                                                            │   weighted RRF → rerank? → threshold/top-k
                                                            │            ▼
                                                            │   prompt assembly (spotlighted Chunks)
                                                            │            ▼
                                                            │   stream answer + citations (SSE)
                                                            │            ▼
                                                            └── persist Message + Trace
```

## 2. Ingestion

The full flow ([plan §2, ingestion](../plan.md#ingestion-pipeline-celery)):

### 2.1 Upload: straight to object storage

1. The Studio asks the API for a presigned PUT URL. The API validates file type (PDF, DOCX, PPTX, HTML, Markdown, TXT) and size **before** the upload starts, so nobody waits for an upload that will fail.
2. The browser uploads straight to S3 (RustFS locally). Large files never pass through the API.
3. The Studio confirms. The API computes the **SHA-256 content hash**, refuses duplicates within the Project (with a link to the existing Document), creates the Document as `Queued`, and enqueues ingestion.

### 2.2 Convert: Docling

The worker sets status to `Processing` and converts the file with **Docling**, which understands layout, headings, tables and slides across formats and outputs structured markdown. OCR runs only if the Project turns it on, because it is slow and most Knowledge Bases don't need it. The converted markdown is stored, so Editors can open the **Document viewer** and check that the conversion read the file correctly. Most "the bot gave a wrong answer" bugs start as bad extraction, and the viewer makes that visible.

Docling is heavy, so its models are baked into the worker image at build time rather than downloaded at startup.

### 2.3 Chunk: structure-aware, tokenizer-matched

Docling's `HybridChunker` splits the document along its structure (sections, headings, tables) and then by token count. Two details matter:

- **The tokenizer matches the Embedding Model.** Chunk sizes are measured in the tokens the embedder will actually see, so Chunks aren't silently truncated at embedding time.
- **Each Chunk keeps its heading path and page range.** That metadata powers citations ("Handbook › Leave › Parental, p. 12") and lets Editors see exactly what an Agent can retrieve.

### 2.4 Embed and scan

Chunks are embedded in batches through an embedder port, and then the **ingestion Guardrail scan** runs the injection classifier over each Chunk to flag text that looks like instructions to an AI. That's the defence against indirect prompt injection hidden in Documents (see the [guardrails write-up](./agentic-guardrails-in-production.md)).

### 2.5 Store atomically

All of a Document's Chunks are written **in one transaction**, then the status becomes `Ready`. A Document is either fully retrievable or not retrievable at all.

### 2.6 Failure handling

Failures are categorised (unsupported content, conversion error, provider error, quota) and set `Failed` with a readable message. Transient errors retry with exponential backoff, and Editors can retry manually. The Document list polls a cheap status endpoint while anything is in flight.

### 2.7 Lifecycle operations without gaps

- **Replacing an edition.** A newer upload creates a *staged* set of Chunks under the same Document identity (Tags and history kept). The old Chunks keep serving until the new set is `Ready`, then the swap happens in one transaction.
- **Deleting.** Chunks are removed in the same transaction as the Document, so retrieval stops immediately. Traces that referenced them keep a **tombstone** ("Chunk from deleted Document *name*") instead of breaking.
- **Quotas** per Project keep storage and processing costs bounded.

## 3. Embeddings: local by default, switchable without downtime

[ADR-0002](../adr/0002-local-embeddings-by-default.md) makes a non-obvious call: every Project embeds with a **platform-run local model** (`multilingual-e5-small`, CPU, ONNX via `fastembed`) unless it opts into Voyage, OpenAI or Bedrock.

Why local by default:

- **Anthropic, a likely chat provider, has no embeddings API**, so the default couldn't depend on the chat credential.
- A new Organisation can **upload Documents before configuring any credential**.
- It costs nothing per Chunk, and it makes tests deterministic.
- It is multilingual out of the box, and the e5 query/passage prefixes are applied correctly.

**The Embedding Model is recorded on every Chunk.** Vectors from different models live in different spaces, and comparing them silently produces garbage. Recording the model means a Project's vectors are never mixed, and every query filters on the active model.

**Re-embedding is a blue/green migration.** When a Project changes model:

1. The new model is set as *pending*, and a background job writes new vectors **alongside** the old ones, with progress shown in the UI.
2. The old vectors keep serving the whole time.
3. Uploads during the job are embedded with **both** models, so nothing is missing after the switch.
4. On completion, the active model flips and the old vectors are deleted **in one transaction**.
5. If the provider fails partway, the Project stays on its previous model and the error is shown.

Agents never answer from a half-migrated Knowledge Base.

## 4. One datastore: Postgres + pgvector, hybrid search

[ADR-0001](../adr/0001-pgvector-hybrid-search.md): Chunks, their vectors and their full-text index all live in the main Postgres database. The `chunks` table holds the text, a pgvector `vector` column, a generated `tsvector` column, heading and page metadata, the Embedding Model ID and Guardrail flags. There is an **HNSW** index on the vectors and a **GIN** index on the `tsvector`.

A dedicated vector database (OpenSearch Serverless, Qdrant, Pinecone) was rejected because Postgres gives:

- **one datastore** to run, back up and test;
- **Document deletion that cascades in one transaction**, which a second store can't do without distributed cleanup;
- **Project isolation with an ordinary `project_id` filter**, enforced by repository functions that require it, and covered by a parametrised cross-tenant test suite.

A specialised engine would pay off only at a scale this product doesn't need.

## 5. Query-time retrieval

Retrieval is a deliberately **deep module** with one operation ([spec 04](../specs/04-agents-retrieval-playground-spec.md)):

```
retrieve(project, query, retrieval settings)
  → ranked candidates with scores
  + excluded candidates with reasons
```

Steps:

1. **Embed the query** with the Project's *active* Embedding Model.
2. **Run two searches in parallel**, each scoped to the Project, the active model and the Agent's Tags:
   - pgvector cosine similarity for *meaning*;
   - Postgres full-text search for *exact terms*: product codes, policy numbers, names. Pure vector search is notoriously weak at these.
3. **Fuse with weighted reciprocal rank fusion (RRF).** RRF combines rankings rather than raw scores, so the two incomparable score scales never need calibrating. The Agent's **hybrid weighting** lets an Editor lean towards keywords or semantics.
4. **Optionally rerank** with a cross-encoder through the model gateway (a Voyage or Bedrock credential with rerank capability) when answer quality matters more than latency.
5. **Apply the minimum relevance threshold and top-k.**

Two tuning features make this production-friendly:

- **Tag scoping** lets several Agents share one Knowledge Base with different views of it (an HR Agent sees only HR-tagged Documents), without duplicating Documents into separate Projects.
- **Excluded candidates are returned, not discarded.** Chunks dropped by the threshold, Tags or the ingestion quarantine appear in the Trace with their reason, so Editors tune retrieval with evidence, not guesswork.

## 6. Generation: grounded, structured, streamed

The Agent runtime is the other deep module: `run_turn(conversation context, AgentConfig, Instructions text, Visitor input) → async stream of events`. It knows nothing about HTTP, the Playground or the widget, so the same code serves both.

**Prompt assembly has a fixed order:**

1. platform preamble (rules for untrusted data, the canary token);
2. the pinned Project Instructions Version (shared rules for every Agent in the Project);
3. the Agent system prompt;
4. the remembered turns (configurable count, to trade context against cost);
5. retrieved Chunks and the Visitor input, each in **labelled, delimited data blocks** ("spotlighting").

**"I don't know" is a feature.** If nothing clears the relevance threshold, the runtime replies with the Agent's configured fallback text instead of letting the model improvise. The **fallback rate** is then tracked per Version as a coverage metric: a rising fallback rate means the Knowledge Base has gaps.

**Citations are resolved, not trusted.** The model is asked to reference Chunk labels, using structured output (Pydantic AI result types) where the provider supports it and label parsing otherwise. Labels are resolved back to real Chunk IDs, so a citation always points at a passage that was actually retrieved. Visitors can expand a citation to see the Document name and passage, and Editors can jump to it in the Document viewer.

**Streaming.** Replies stream over Server-Sent Events as `token`, `citation`, `done` and `error` events. Provider failures (invalid key, rate limit, model unavailable) become typed error events rather than broken streams.

## 7. Every answer has a Trace

After generation, the Message is persisted with a full **Trace**: provider, model, Agent Version, input, output and cached tokens, **cost frozen** from the price table at write time, time to first token, total latency, every retrieved Chunk with its score and rank and whether it was cited, excluded Chunks with reasons, and Guardrail outcomes.

This is what makes the RAG pipeline debuggable. "Why did it say that?" has a concrete answer for every reply:

| Symptom | Where the Trace points |
|---|---|
| Wrong facts | Retrieved Chunks were wrong → tune weighting, threshold or Tags, or fix the Document |
| "I don't know" on a covered topic | The right Chunk was excluded by the threshold, or never extracted (check the Document viewer) |
| Right Chunk retrieved but ignored | Retrieved but not cited → a prompt problem, not a retrieval problem |
| Slow replies | Time to first token versus reranker and model latency |

## 8. Changing behaviour safely: versions and measurement

A RAG system's behaviour depends on its prompt, model, retrieval settings and shared instructions. [ADR-0003](../adr/0003-immutable-versions-with-live-pointer.md) makes that a single, comparable unit:

- An Agent has one Draft and **immutable, numbered Versions**. Publishing creates a Version and points **Live** at it; reverting moves the pointer back, taking effect on the very next reply.
- Each Agent Version **pins** a Project Instructions Version, so a Version fully describes behaviour, and reverting an Agent also restores the Instructions it ran with.
- The **Playground** lets Editors chat with the Draft before publishing. Playground traffic is flagged and excluded from metrics and the Token Budget.
- **Analytics compare Versions side by side**: volume, cost, thumbs-up rate with Wilson 95% intervals and sample sizes, mean rating, fallback rate, Guardrail block rate and latency, plus a time series marked wherever the Live pointer moved.

One known confounder is stated openly: **Documents are not versioned.** The Knowledge Base is live and shared, so a Version comparison can be affected by Documents changing underneath it.

## 9. Testing a RAG pipeline deterministically

Every external system sits behind a port with a deterministic fake ([shared test seams](../specs/README.md#shared-test-seams)):

| Port | Production | Test fake |
|---|---|---|
| Document converter | Docling | Fixed markdown and structure (plus a committed fixture of real Docling output for the chunker) |
| Embedder | Local e5, Voyage, OpenAI, Bedrock | Deterministic hash-based embedder |
| Chat model | Pydantic AI providers | `TestModel` / `FunctionModel` |
| Injection classifier | ONNX, LLM | Rule-driven fake |

Retrieval is tested against **real Postgres with pgvector** on a fixture Knowledge Base with known relevant and irrelevant Chunks, covering semantic hits, keyword-only hits, the effect of weighting, Tag scoping, the threshold triggering the fallback, reranker reordering, and Project and Embedding Model isolation. A prompt-assembly contract test uses an echoing model to prove every block reaches the model in the right order. Real Docling, real embeddings and real providers run in a nightly `live` suite outside the coverage gate.

## 10. Takeaways

1. **Extraction quality caps answer quality.** Use a layout-aware converter, and show people the converted output.
2. **Chunk by structure and by the embedder's tokens**, and keep heading and page metadata for citations.
3. **Record the Embedding Model on every vector**, and migrate models blue/green.
4. **Hybrid search with RRF** fixes vector search's blind spot for exact terms without score calibration.
5. **Keep vectors in your main database** until scale proves otherwise: transactional deletes and simple isolation are worth more than raw ANN speed.
6. **Make "I don't know" an explicit, measured outcome** driven by a relevance threshold.
7. **Resolve citations to real Chunk IDs**, and keep a Trace for every answer, including what was *excluded*.
8. **Version the whole behaviour** and compare Versions with confidence intervals, not anecdotes.
