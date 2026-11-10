import { useParams } from "@tanstack/react-router";
import { useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Badge, button, EmptyState, FlagCount, Notice, Pagination, Skeleton, Status, surface, text } from "../design";
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
import { fileType, formatSize, STATUS_LABELS, STATUS_TONES } from "./DocumentsTab";

type Chunk = ChunkPage["items"][number];

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
    <div className="flex flex-col items-start gap-2 rounded-xl bg-flag-soft px-3.5 py-2.5 text-sm text-flag">
      <p role="note" aria-label="Guardrail flag">
        <strong className="font-medium">Flagged:</strong> {FLAG_LABELS[flag.label] ?? flag.label}, score {flag.score.toFixed(2)}. {flag.reason}
      </p>
      {clear.error && <Notice tone="error">{clearFlagFailure(clear.error)}</Notice>}
      <button
        type="button"
        className={button.secondary}
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
  // A flagged Chunk's card is edged in the flag colour and badged, so it stands out while scrolling.
  const border = chunk.flag ? "border-flag" : "border-line";
  return (
    <li className={`flex flex-col gap-2 rounded-2xl border bg-surface p-4 text-sm ${border}`}>
      <p className="flex items-center gap-2 font-mono text-xs text-muted">
        Chunk {chunk.ordinal + 1}
        {chunk.flag && <Badge kind="flagged" />}
      </p>
      {chunk.heading_path.length > 0 && <p className="font-medium text-ink">{chunk.heading_path.join(" › ")}</p>}
      {pages && <p className="text-xs text-muted">{pages}</p>}
      {chunk.flag && <FlagNote flag={chunk.flag} chunk={chunk} at={at} />}
      <p className="whitespace-pre-wrap text-ink-2">{chunk.text}</p>
    </li>
  );
}

function ChunkList({ organisationId, projectId, documentId }: { organisationId: string; projectId: string; documentId: string }) {
  const [page, setPage] = useState(0);
  const chunks = useChunkPage(organisationId, projectId, documentId, page);

  let body;
  if (chunks.isError) {
    body = <Notice tone="error">The Chunks could not be loaded. Try again shortly.</Notice>;
  } else if (chunks.data === undefined) {
    body = <Skeleton label="Loading Chunks" />;
  } else if (chunks.data.total === 0) {
    body = <p className={text.muted}>This Document has no Chunks yet.</p>;
  } else {
    const { items, total, offset } = chunks.data;
    const pageCount = Math.ceil(total / CHUNK_PAGE_SIZE);
    body = (
      <>
        <p className={text.muted}>
          Chunks {offset + 1}–{offset + items.length} of {total}
        </p>
        <ol aria-label="Chunks on this page" className="flex flex-col gap-3">
          {items.map((chunk) => (
            <ChunkItem key={chunk.id} chunk={chunk} at={{ organisationId, projectId, documentId }} />
          ))}
        </ol>
        <Pagination
          label="Chunk pages"
          page={page + 1}
          pageCount={pageCount}
          onPageChange={(next) => {
            setPage(next - 1);
          }}
        />
      </>
    );
  }

  return (
    <section aria-labelledby="chunks-heading" className="flex min-w-0 flex-col gap-3">
      <h3 id="chunks-heading" className={text.heading}>
        Chunks
      </h3>
      {body}
    </section>
  );
}

function DocumentHeader({ document, download }: { document: DocumentDetail; download: string }) {
  const chunks = document.chunk_count;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 flex-col gap-2">
          <h2 className="text-2xl font-medium tracking-[-0.01em] text-ink">{document.name}</h2>
          <ul aria-label="Document details" className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted">
            <li>
              <Status tone={STATUS_TONES[document.status]}>
                {STATUS_LABELS[document.status]}
                {document.error_message && `: ${document.error_message}`}
              </Status>
            </li>
            <li className="font-mono text-xs">{fileType(document.name)}</li>
            <li className="font-mono text-xs">{formatSize(document.size_bytes)}</li>
            <li className="font-mono text-xs">{`${String(chunks)} ${chunks === 1 ? "chunk" : "chunks"}`}</li>
            {document.flagged_chunk_count > 0 && (
              <li>
                <FlagCount count={document.flagged_chunk_count} label="flagged chunks" />
              </li>
            )}
          </ul>
        </div>
        <a href={download} download={document.name} className={button.secondary}>
          Download original
        </a>
      </div>
      {document.flagged_chunk_count > 0 && (
        <Notice tone="warning">
          {document.flagged_chunk_count} {document.flagged_chunk_count === 1 ? "Chunk" : "Chunks"} flagged as possible
          instructions to an AI.
        </Notice>
      )}
    </div>
  );
}

/**
 * The Document viewer: Docling's converted markdown beside the Document's Chunks, each on a card
 * with its heading path and pages, so an Editor sees exactly what an Agent can retrieve. Chunks the
 * ingestion Guardrail scan flagged are badged and say why.
 */
export function DocumentViewer() {
  const { organisationId, projectId, documentId } = useParams({
    from: "/signed-in/organisations/$organisationId/projects/$projectId/documents/$documentId",
  });
  const document = useDocument(organisationId, projectId, documentId);

  let content;
  if (document.isError) {
    content = <EmptyState tone="error" title="This Document could not be loaded" description="It may have been removed." />;
  } else if (document.data === undefined) {
    content = <Skeleton label="Loading the Document" />;
  } else {
    content = (
      <>
        <DocumentHeader document={document.data} download={downloadPath(organisationId, projectId, documentId)} />
        <div className="grid gap-6 lg:grid-cols-2">
          <section aria-labelledby="markdown-heading" className="flex min-w-0 flex-col gap-3">
            <h3 id="markdown-heading" className={text.heading}>
              Converted markdown
            </h3>
            {document.data.markdown === null ? (
              <p className={text.muted}>There is no converted markdown yet.</p>
            ) : (
              // It scrolls on its own, so it takes focus for keyboard scrolling (WCAG 2.1.1).
              <div tabIndex={0} className={`${surface.panel} markdown max-h-[70vh] overflow-auto text-sm`}>
                <Markdown remarkPlugins={[remarkGfm]}>{document.data.markdown}</Markdown>
              </div>
            )}
          </section>
          <ChunkList organisationId={organisationId} projectId={projectId} documentId={documentId} />
        </div>
      </>
    );
  }

  // The breadcrumb's Document crumb names it, and its Documents crumb leads back to the list.
  return <div className="flex flex-col gap-6">{content}</div>;
}
