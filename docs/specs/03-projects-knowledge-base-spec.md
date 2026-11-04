# Spec 03: Projects and Knowledge Base

## Problem Statement

An Organisation's Agents are only as good as the material they can retrieve from, and that material is scattered across PDFs, slide decks, Word documents and web pages. Teams need somewhere to collect it for a particular purpose (HR, product support, sales), kept strictly apart from other purposes. They need to know it was processed correctly and to be able to see exactly what the Agent will retrieve. Uploads can fail, documents get revised, and some uploaded documents may contain text written to manipulate an AI. Without visibility into processing and the resulting Chunks, Members are flying blind.

## Solution

Members create Projects, each an isolated container of a Knowledge Base, its Project Instructions and its Agents (Instructions arrive in spec 04/05, Agents in spec 04). Uploading Documents to a Project:
- **Upload and process.** Files go straight to object storage, a Celery worker converts them with Docling, and they're chunked with Docling's `HybridChunker`.
- **Embed and scan.** Chunks are embedded with the Project's Embedding Model and scanned for instruction-like text.
- **Track status.** Every Document shows its status (Queued, Processing, Ready, Failed) and can be retried, replaced with a newer edition or deleted, with deletion taking effect for retrieval immediately.

The Document viewer shows the converted markdown next to its Chunks, with any Guardrail flags and the Document's Tags. Each Project chooses an Embedding Model: the platform's local model by default, or Voyage, OpenAI or Bedrock through a Provider Credential. Changing it re-embeds the Knowledge Base in the background while the old vectors keep serving.

## User Stories

1. As an Editor, I want to create a Project with a name and description, so that I can collect knowledge for one purpose.
2. As an Editor, I want Projects strictly isolated from each other, so that an HR Agent can never retrieve sales material.
3. As an Editor, I want to see all active Projects in my Organisation with Document and Agent counts, so that I can find what I need.
4. As an Editor, I want to rename a Project and edit its description, so that it stays accurately labelled.
5. As an Editor, I want to Archive a Project, so that it disappears from the main list and stops serving without losing its history.
6. As an Owner, I want to restore an archived Project, so that archiving by mistake is recoverable.
7. As an Owner, I want to permanently delete an archived Project after typing its name, so that data is gone when we truly need it gone.
8. As an Editor, I want to drag and drop several files to upload at once, so that building a Knowledge Base is fast.
9. As an Editor, I want uploads of PDF, DOCX, PPTX, HTML, Markdown and TXT accepted, and anything else refused with a clear message, so that I know what's supported.
10. As an Editor, I want files over the size limit refused before uploading, so that I don't wait for an upload that will fail.
11. As an Editor, I want a per-file upload progress bar, so that I know large files are progressing.
12. As an Editor, I want each Document's status shown (Queued, Processing, Ready, Failed) and updated without refreshing, so that I know when it's usable.
13. As an Editor, I want a readable error when a Document fails, so that I know whether to fix the file or retry.
14. As an Editor, I want to retry a failed Document, so that transient failures don't force a re-upload.
15. As an Editor, I want uploading an identical file to be detected and refused as a duplicate, with a link to the existing Document, so that the Knowledge Base doesn't fill with copies.
16. As an Editor, I want to upload a newer edition of a Document to replace it in place, so that its identity, Tags and history are kept while its content is refreshed.
17. As an Editor, I want the old edition to keep serving until the new one is Ready, so that replacing a Document never leaves a gap.
18. As an Editor, I want to delete a Document and have it stop being retrieved immediately, so that wrong or sensitive content can be removed fast.
19. As an Editor, I want to filter and search the Document list by name, status and Tag, so that large Knowledge Bases stay manageable.
20. As an Editor, I want to create, rename and delete Tags in a Project, so that I can organise Documents by topic or audience.
21. As an Editor, I want to apply several Tags to a Document, and to many Documents at once, so that tagging scales.
22. As an Editor, I want to open a Document and see the converted markdown, so that I can confirm Docling read it correctly.
23. As an Editor, I want to see the Document's Chunks next to the markdown, with heading context and page numbers, so that I understand exactly what an Agent can retrieve.
24. As an Editor, I want Chunks that look like instructions to an AI flagged in the viewer with the reason, so that I can spot indirect prompt-injection attempts hidden in documents.
25. As an Editor, I want to see how many Chunks are flagged per Document in the list, so that risky Documents stand out.
26. As an Editor, I want to download the original file, so that I can compare it with the converted output.
27. As an Editor, I want to turn on OCR per Project, so that scanned PDFs are readable when we need them, without slowing every Project down.
28. As an Editor, I want new Projects to use the platform's local Embedding Model by default, so that uploading works before any Provider Credential is set up.
29. As an Editor, I want to choose a Voyage, OpenAI or Bedrock Embedding Model from the Organisation's embedding-capable credentials, so that we can use higher-quality embeddings when we want to.
30. As an Editor, I want changing the Embedding Model to re-embed the whole Knowledge Base in the background with visible progress, so that switching models is safe.
31. As an Editor, I want retrieval to keep using the old vectors until re-embedding finishes and then switch over in one step, so that Agents never answer from a half-migrated Knowledge Base.
32. As an Editor, I want a failed re-embed to leave the Project on its previous Embedding Model with the error shown, so that a provider outage can't break retrieval.
33. As an Editor, I want uploads during a re-embed to be embedded with both models, so that nothing is missing after the switch.
34. As an Owner, I want a per-Project Document quota enforced with a clear message, so that storage and processing costs stay bounded.
35. As an Owner, I want Project create, archive, restore and delete, Embedding Model changes, and Document deletes recorded as Audit Events, so that changes to the Knowledge Base are traceable.
36. As a Member, I want a Project page with tabs for Documents, Instructions, Agents, Conversations and Analytics, so that everything about a Project is in one place as features arrive.

## Implementation Decisions

- **Projects module.** CRUD, Archive (an `archived_at` timestamp), restore, and permanent deletion for Owners. Permanent deletion cascades to Documents, Chunks and stored objects through a Celery task. A Project holds:
  - the active Embedding Model reference, and a pending one while a re-embed runs;
  - the OCR flag;
  - the Document quota;
  - a Current Project Instructions Version reference, empty until spec 05.
- **Tags.** Scoped to a Project, with a many-to-many link to Documents. Agents reference Tags in spec 04.
- **Upload flow.**
  1. The Studio asks the API for a presigned PUT, which validates the file type and size up front.
  2. The browser uploads straight to the object store.
  3. The Studio confirms the upload. The API computes or verifies the SHA-256 content hash, checks for duplicates within the Project, creates the Document as Queued, and enqueues ingestion.
  The object store port has S3 and RustFS (same adapter, different endpoint) and an in-memory fake.
- **Document model.** Name, MIME type, size, content hash, object key, status, error message, attempt count, the stored converted markdown's object key, and the current edition number.
  - **Replacing an edition** creates a staged set of Chunks under the same Document. When it reaches Ready, the swap happens in one transaction. Until then, the old Chunks stay retrievable.
- **Ingestion pipeline (Celery task).**
  1. Set status to Processing.
  2. Fetch the original file and convert it through the document-converter port: Docling, with OCR only if the Project's flag is on.
  3. Store the markdown.
  4. Chunk it with `HybridChunker`, using a tokenizer that matches the Embedding Model (local model tokenizer, or a provider's documented tokenizer or approximation), with a max-tokens setting.
  5. Embed through the embedder port, batched.
  6. Run the ingestion Guardrail scan through the injection-classifier port: the local classifier, or the rule-driven fake in tests. Spec 08 hardens the classifier; this slice ships the scan hook and a heuristic baseline.
  7. Write the Chunks in one transaction and set status to Ready.
  Failures are categorised (unsupported content, conversion error, provider error, quota) and set status to Failed with a readable message. Retries use exponential backoff for transient errors.
- **Chunk model.** Project ID, Document ID, edition, ordinal, text, heading path, page range, a `vector` column (pgvector; dimension per Embedding Model), Embedding Model ID, a generated `tsvector` column for full-text search, and Guardrail flags (classifier label, score, reason). An HNSW index sits on the vectors, filtered by Embedding Model, and a GIN index on the `tsvector` (ADR-0001).
- **Embedding Model registry.** Lists the available Embedding Models with provider, dimension, tokenizer and required capability. The local model is `multilingual-e5-small`, through `fastembed`, with the right query/passage prefixes. Provider models resolve through spec 02's model gateway.
- **Re-embed job.** Choosing a new Embedding Model sets it as pending and enqueues a job that walks every Ready Chunk, writes new vectors alongside the existing ones (rows tagged with the pending model), reports progress, and finally switches active to pending and deletes the old vectors in one transaction. New uploads during the job embed with both models (ADR-0002).
- **Deletion.** Deleting a Document removes its Chunks in the same transaction, so retrieval stops at once, and schedules deletion of the stored objects. Traces keep tombstones (spec 07).
- **Status updates.** The Document list polls a lightweight status endpoint while any Document isn't in a final state. SSE isn't needed here.
- **Studio UI.** Projects list, Project page tabs, Documents table with filters and bulk tagging, upload dropzone, Document viewer (markdown pane plus Chunk list with flags), Project settings (Embedding Model with re-embed progress, OCR toggle, quota display).

## Testing Decisions

- **Good tests** observe Document status, Chunks and flags through the API, as an Editor would. They don't assert how many times the converter was called or how batches are split.
- **API seam plus task seam:** upload (presign → put to RustFS in integration tests or the in-memory store in unit tests → confirm) runs ingestion eagerly using the fake converter, the deterministic embedder and the rule-driven classifier. Then the test asserts status Ready, the Chunk list, flags and Tags through the API. Failure categories come from configuring the fakes to raise.
- **Edge cases:** duplicate hash refused; replacing an edition keeps the old Chunks retrievable until the swap; delete removes Chunks immediately; quota refusal; archive hides the Project and blocks uploads; restore; permanent delete cascades; cross-Project and cross-tenant isolation added to the parametrised suite.
- **Re-embed:** start the switch, check the old vectors still serve through a minimal retrieval probe endpoint (also used by spec 04), complete the job and confirm the switch, simulate a provider failure partway and confirm the Project stays on the old model, and confirm uploads during the job get both vectors.
- **Chunking:** tested once at the converter-plus-chunker seam with a small fixture of real Docling output (recorded from a live run and committed), so tests don't depend on Docling at runtime. A live-suite test runs real Docling on sample PDF, DOCX and PPTX fixtures.
- **Frontend, network seam:** dropzone validation messages, progress, status updates while polling, failure plus retry, the viewer showing flags, bulk tagging, re-embed progress and failure messages.
- **End-to-end:** upload the seed handbook; it reaches Ready; open the viewer; a planted injection Chunk is flagged.
- **Prior art:** spec 01 fixtures, and spec 02's model gateway fakes for provider Embedding Models.

## Out of Scope

- XLSX and image ingestion.
- Versioning Documents (ADR-0003). Only the current edition is kept.
- Crawling URLs or syncing from external sources (Google Drive, Confluence).
- Editing a Document's content or Chunks by hand.
- Retrieval used by Agents (spec 04). This slice only exposes a minimal retrieval probe for testing re-embedding.

## Further Notes

- Docling is heavy. The worker image bundles its models at build time to avoid downloads at startup. Model downloads in CI are cached.
- The heuristic ingestion scan here is deliberately simple. Spec 08 swaps in the ONNX classifier behind the same port without changing this slice's behaviour or tests.
