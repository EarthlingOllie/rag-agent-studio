import { Link, useParams } from "@tanstack/react-router";
import { useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { FormError } from "../auth/AuthLayout";
import {
  type ChunkPage,
  type DocumentDetail,
  CHUNK_PAGE_SIZE,
  clearFlagFailure,
  downloadPath,
  useChunkPage,
  useClearChunkFlag,
  useDocument,
} from "./documents";
import { STATUS_LABELS } from "./DocumentsTab";
import { BUTTON } from "./ProjectsPage";

type Chunk = ChunkPage["items"][number];

const PROJECT = "/organisations/$organisationId/projects/$projectId";

/** "Page 3", "Pages 3–4", or nothing for formats without pages. */
function pageLabel({ page_start: start, page_end: end }: Chunk): string | null {
  if (start === null) return null;
  return end === null || end === start ? `Page ${String(start)}` : `Pages ${String(start)}–${String(end)}`;
}

/** How the Studio names the injection classifier's labels; any other label shows as given. */
const FLAG_LABELS: Record<string, string> = { prompt_injection: "Prompt injection" };

interface DocumentRef {
  organisationId: string;
  projectId: string;
  documentId: string;
}

/**
 * Why the ingestion Guardrail scan flagged the Chunk as instructions aimed at an AI, and a button
 * to clear the flag when it is a false positive (audited; the Chunk is then retrieved again).
 */
function FlagNote({ flag, chunk, at }: { flag: NonNullable<Chunk["flag"]>; chunk: Chunk; at: DocumentRef }) {
  const clear = useClearChunkFlag(at.organisationId, at.projectId, at.documentId);
  return (
    <div className="space-y-2 rounded bg-amber-50 p-2 text-amber-900">
      <p role="note" aria-label="Guardrail flag">
        <strong>Flagged:</strong> {FLAG_LABELS[flag.label] ?? flag.label}, score {flag.score.toFixed(2)}. {flag.reason}
      </p>
      <FormError message={clearFlagFailure(clear.error)} />
      <button
        type="button"
        className={BUTTON}
        aria-label={`Clear flag on Chunk ${String(chunk.ordinal + 1)}`}
        disabled={clear.isPending}
        onClick={() => {
          clear.mutate(chunk.id);
        }}
      >
        Clear flag
      </button>
    </div>
  );
}

function ChunkItem({ chunk, at }: { chunk: Chunk; at: DocumentRef }) {
  const pages = pageLabel(chunk);
  const border = chunk.flag ? "border-amber-500" : "border-slate-200";
  return (
    <li className={`space-y-1 rounded border p-3 text-sm ${border}`}>
      <p className="text-xs font-medium text-slate-700">Chunk {chunk.ordinal + 1}</p>
      {chunk.heading_path.length > 0 && <p className="font-medium text-slate-900">{chunk.heading_path.join(" › ")}</p>}
      {pages && <p className="text-xs text-slate-700">{pages}</p>}
      {chunk.flag && <FlagNote flag={chunk.flag} chunk={chunk} at={at} />}
      <p className="whitespace-pre-wrap text-slate-900">{chunk.text}</p>
    </li>
  );
}

function ChunkList({ organisationId, projectId, documentId }: { organisationId: string; projectId: string; documentId: string }) {
  const [page, setPage] = useState(0);
  const chunks = useChunkPage(organisationId, projectId, documentId, page);

  let body;
  if (chunks.isError) {
    body = <p role="alert">The Chunks could not be loaded. Try again shortly.</p>;
  } else if (chunks.data === undefined) {
    body = <p role="status">Loading Chunks…</p>;
  } else if (chunks.data.total === 0) {
    body = <p className="text-slate-700">This Document has no Chunks yet.</p>;
  } else {
    const { items, total, offset } = chunks.data;
    const pageCount = Math.ceil(total / CHUNK_PAGE_SIZE);
    body = (
      <>
        <p className="text-sm text-slate-700">
          Chunks {offset + 1}–{offset + items.length} of {total}
        </p>
        <ol className="space-y-2">
          {items.map((chunk) => (
            <ChunkItem key={chunk.id} chunk={chunk} at={{ organisationId, projectId, documentId }} />
          ))}
        </ol>
        {pageCount > 1 && (
          <nav aria-label="Chunk pages" className="flex gap-2">
            <button
              type="button"
              className={BUTTON}
              disabled={page === 0}
              onClick={() => {
                setPage(page - 1);
              }}
            >
              Previous
            </button>
            <button
              type="button"
              className={BUTTON}
              disabled={page + 1 >= pageCount}
              onClick={() => {
                setPage(page + 1);
              }}
            >
              Next
            </button>
          </nav>
        )}
      </>
    );
  }

  return (
    <section aria-labelledby="chunks-heading" className="space-y-3">
      <h3 id="chunks-heading" className="font-semibold">
        Chunks
      </h3>
      {body}
    </section>
  );
}

function DocumentHeader({ document, download }: { document: DocumentDetail; download: string }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-3">
      <div>
        <h2 className="text-lg font-semibold">{document.name}</h2>
        <p className="text-sm text-slate-700">
          {STATUS_LABELS[document.status]}
          {document.error_message && `: ${document.error_message}`}
        </p>
        {document.flagged_chunk_count > 0 && (
          <p className="text-sm font-medium text-amber-900">
            {document.flagged_chunk_count} {document.flagged_chunk_count === 1 ? "Chunk" : "Chunks"} flagged as possible
            instructions to an AI.
          </p>
        )}
      </div>
      <a href={download} download={document.name} className={BUTTON}>
        Download original
      </a>
    </div>
  );
}

/**
 * The Document viewer: Docling's converted markdown beside the Document's Chunks, each with its
 * heading path and pages, so an Editor sees exactly what an Agent can retrieve. Chunks the
 * ingestion Guardrail scan flagged say why.
 */
export function DocumentViewer() {
  const { organisationId, projectId, documentId } = useParams({
    from: "/signed-in/organisations/$organisationId/projects/$projectId/documents/$documentId",
  });
  const document = useDocument(organisationId, projectId, documentId);

  let content;
  if (document.isError) {
    content = <p role="alert">This Document could not be loaded. It may have been removed.</p>;
  } else if (document.data === undefined) {
    content = <p role="status">Loading Document…</p>;
  } else {
    content = (
      <>
        <DocumentHeader document={document.data} download={downloadPath(organisationId, projectId, documentId)} />
        <div className="grid gap-6 lg:grid-cols-2">
          <section aria-labelledby="markdown-heading" className="min-w-0 space-y-3">
            <h3 id="markdown-heading" className="font-semibold">
              Converted markdown
            </h3>
            {document.data.markdown === null ? (
              <p className="text-slate-700">There is no converted markdown yet.</p>
            ) : (
              // It scrolls on its own, so it takes focus for keyboard scrolling (WCAG 2.1.1).
              <div tabIndex={0} className="markdown max-h-[70vh] overflow-auto rounded border border-slate-200 p-4 text-sm">
                <Markdown remarkPlugins={[remarkGfm]}>{document.data.markdown}</Markdown>
              </div>
            )}
          </section>
          <ChunkList organisationId={organisationId} projectId={projectId} documentId={documentId} />
        </div>
      </>
    );
  }

  return (
    <div className="space-y-4">
      <Link to={PROJECT} params={{ organisationId, projectId }} className="text-sm underline">
        All Documents
      </Link>
      {content}
    </div>
  );
}
