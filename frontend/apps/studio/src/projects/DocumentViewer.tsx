import { useParams } from "@tanstack/react-router";
import { type ComponentProps, useState } from "react";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { Badge, button, ConfirmDialog, EmptyState, field, FlagCount, Notice, Pagination, Skeleton, Status, surface, text } from "../design";
import { formatTime } from "../settings/AuditPage";
import {
  type ChunkPage,
  type DocumentDetail,
  allowFailure,
  CHUNK_PAGE_SIZE,
  downloadPath,
  useAllowChunk,
  useChunkPage,
  useDocument,
} from "./documents";
import { fileType, formatSize, STATUS_LABELS, STATUS_TONES } from "./DocumentsTab";

type Chunk = ChunkPage["items"][number];

/** A heading of the Document's markdown, rendered as `Tag` but looking like the level it was written at. */
function demoted(Tag: "h4" | "h5" | "h6", look: string) {
  return function DemotedHeading(props: ComponentProps<"h1"> & { node?: unknown }) {
    // react-markdown also passes its syntax-tree node, which is not an HTML attribute.
    const attributes = { ...props };
    delete attributes.node;
    return <Tag {...attributes} className={look} />;
  };
}

/**
 * The Document's headings sit below the page's own (the Project's h1, the Document's h2 and the
 * "Converted markdown" h3), so a Document's "# Title" never makes a second h1 on the page (WCAG 1.3.1).
 */
const DOCUMENT_HEADINGS: Components = {
  h1: demoted("h4", "text-xl font-semibold"),
  h2: demoted("h5", "text-lg font-semibold"),
  h3: demoted("h6", "font-semibold"),
  h4: demoted("h6", "font-semibold"),
  h5: demoted("h6", "font-semibold"),
  h6: demoted("h6", "font-semibold"),
};

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

type Flag = NonNullable<Chunk["flag"]>;

/** "Prompt injection, score 0.96. <reason>": what the ingestion Guardrail scan said about the Chunk. */
function verdict(flag: Flag): string {
  return `${FLAG_LABELS[flag.label] ?? flag.label}, score ${flag.score.toFixed(2)}. ${flag.reason}`;
}

/**
 * Why the ingestion Guardrail scan flagged the Chunk as instructions aimed at an AI. A flagged Chunk
 * is quarantined: Agents never use it. An Editor who judges the flag a false positive allows that one
 * Chunk, after confirming with its text in front of them (audited; the flag is kept, with who
 * allowed it and when).
 */
function FlagNote({ flag, chunk, at }: { flag: Flag; chunk: Chunk; at: DocumentRef }) {
  const allow = useAllowChunk(at.organisationId, at.projectId, at.documentId);
  const [confirming, setConfirming] = useState(false);
  const number = String(chunk.ordinal + 1);
  if (flag.allowed) {
    const by = flag.allowed.allowed_by?.name ?? "a former Member";
    return (
      <p role="note" aria-label="Guardrail flag" className="rounded-xl bg-sunken px-3.5 py-2.5 text-sm text-ink-2">
        <strong className="font-medium">
          Allowed by {by} on {formatTime(flag.allowed.allowed_at)}:
        </strong>{" "}
        {verdict(flag)}
      </p>
    );
  }
  return (
    <div className="flex flex-col items-start gap-2 rounded-xl bg-flag-soft px-3.5 py-2.5 text-sm text-flag">
      <p role="note" aria-label="Guardrail flag">
        <strong className="font-medium">Quarantined:</strong> {verdict(flag)}
      </p>
      {allow.error && <Notice tone="error">{allowFailure(allow.error)}</Notice>}
      <button
        type="button"
        className={button.secondary}
        aria-label={`Allow Chunk ${number}`}
        disabled={allow.isPending}
        onClick={() => {
          setConfirming(true);
        }}
      >
        Allow…
      </button>
      <ConfirmDialog
        open={confirming}
        title={`Allow Chunk ${number} into the knowledge base?`}
        confirmLabel="Allow Chunk"
        busy={allow.isPending}
        body={<p className={`${surface.panel} max-h-48 overflow-auto whitespace-pre-wrap text-sm text-ink-2`}>{chunk.text}</p>}
        onConfirm={() => {
          setConfirming(false);
          allow.mutate(chunk.id);
        }}
        onCancel={() => {
          setConfirming(false);
        }}
      >
        The ingestion Guardrail flagged it: {verdict(flag)} Agents will use this Chunk in their answers once you allow it.
        Allow it only if you have read it and it holds no instructions to an AI. Your name is recorded with the allow.
      </ConfirmDialog>
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
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const chunks = useChunkPage(organisationId, projectId, documentId, page, flaggedOnly);

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
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 id="chunks-heading" className={text.heading}>
          Chunks
        </h3>
        <label className="flex items-center gap-2 text-sm text-ink-2">
          <input
            type="checkbox"
            className={field.checkbox}
            checked={flaggedOnly}
            onChange={(event) => {
              setFlaggedOnly(event.target.checked);
              setPage(0);
            }}
          />
          Only flagged Chunks
        </label>
      </div>
      {body}
    </section>
  );
}

function DocumentHeader({ document, download }: { document: DocumentDetail; download: string }) {
  const chunks = document.chunk_count;
  const quarantined = document.quarantined_chunk_count;
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
            {document.quarantined_chunk_count > 0 && (
              <li>
                <FlagCount count={document.quarantined_chunk_count} label="quarantined chunks" />
              </li>
            )}
          </ul>
        </div>
        <a href={download} download={document.name} className={button.secondary}>
          Download original
        </a>
      </div>
      {quarantined > 0 && (
        <Notice tone="warning">
          {quarantined === 1
            ? "1 Chunk quarantined as possible instructions to an AI: Agents never use it until an Editor reviews and allows it."
            : `${String(quarantined)} Chunks quarantined as possible instructions to an AI: Agents never use them until an Editor reviews and allows them.`}
        </Notice>
      )}
    </div>
  );
}

/**
 * The Document viewer: Docling's converted markdown beside the Document's Chunks, each on a card
 * with its heading path and pages, so an Editor sees exactly what an Agent can retrieve. Chunks the
 * ingestion Guardrail scan flagged are badged, quarantined and say why; an Editor reviews them here and
 * may allow one as a false positive.
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
                <Markdown remarkPlugins={[remarkGfm]} components={DOCUMENT_HEADINGS}>
                  {document.data.markdown}
                </Markdown>
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
