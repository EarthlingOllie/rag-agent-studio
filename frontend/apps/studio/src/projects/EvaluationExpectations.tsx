import { useId, useState } from "react";

import { Badge, Notice, Pagination, Skeleton, button, field, text } from "../design";
import { CHUNK_PAGE_SIZE, useChunkPage, useDocuments } from "./documents";
import type { EvaluationExpectedSource } from "./evaluation";

/** The longest passage an Expected source holds. */
export const PASSAGE_MAX = 1000;

/** An Expected source in the case editor: one already saved (its Document may be gone), or one just picked. */
export type ChosenSource = Pick<EvaluationExpectedSource, "document_id" | "document_name" | "passage"> & {
  stale?: boolean;
  stale_reason?: string | null;
};

/** Why an Expected source is a Stale expectation, in words: its Document is gone (`document_deleted`), or its passage (`passage_missing`). */
export function staleReason(source: { stale_reason?: string | null }): string {
  return source.stale_reason === "document_deleted"
    ? "Its Document has been deleted."
    : "No Chunk of its Document's current Edition holds this passage.";
}

/** The Stale expectation badge, its reason as the hover text. */
export function StaleBadge({ title }: { title: string }) {
  return <Badge kind="staleExpectation" title={title} />;
}

/** One page of a Document's current Chunks, each one choosable as the passage. */
function ChunkChoices({
  organisationId,
  projectId,
  documentId,
  onChoose,
}: {
  organisationId: string;
  projectId: string;
  documentId: string;
  onChoose: (text: string) => void;
}) {
  const [page, setPage] = useState(0);
  const chunks = useChunkPage(organisationId, projectId, documentId, page);
  if (chunks.isError) return <Notice tone="error">The Chunks could not be loaded. Try again shortly.</Notice>;
  if (chunks.data === undefined) return <Skeleton label="Loading Chunks" />;
  if (chunks.data.total === 0) return <p className={text.muted}>This Document has no Chunks yet.</p>;
  const { items, total } = chunks.data;
  return (
    <div className="flex flex-col gap-2">
      <ol aria-label="Chunks" className="flex max-h-72 flex-col gap-2 overflow-y-auto">
        {items.map((chunk) => (
          <li key={chunk.id} className="flex flex-col gap-1.5 rounded-xl bg-sunken px-3.5 py-2.5">
            <p className="text-sm whitespace-pre-wrap text-ink">{chunk.text}</p>
            <button
              type="button"
              className={`${button.quiet} self-start`}
              aria-label={`Use Chunk ${String(chunk.ordinal + 1)} as the passage`}
              onClick={() => {
                onChoose(chunk.text.slice(0, PASSAGE_MAX));
              }}
            >
              Use this Chunk
            </button>
          </li>
        ))}
      </ol>
      <Pagination
        label="Chunk pages"
        page={page + 1}
        pageCount={Math.ceil(total / CHUNK_PAGE_SIZE)}
        onPageChange={(next) => {
          setPage(next - 1);
        }}
      />
    </div>
  );
}

/**
 * The Expected source picker: a Ready Document of the Project, then its current Chunks, one of
 * which fills the passage; the passage can be trimmed to the words that matter before adding it.
 */
export function ExpectedSourcePicker({
  organisationId,
  projectId,
  onAdd,
  onCancel,
}: {
  organisationId: string;
  projectId: string;
  onAdd: (source: ChosenSource) => void;
  onCancel: () => void;
}) {
  const groupId = useId();
  const hintId = useId();
  const errorId = useId();
  const documents = useDocuments(organisationId, projectId);
  const ready = (documents.data ?? []).filter((document) => document.status === "ready");
  const [documentId, setDocumentId] = useState("");
  const [passage, setPassage] = useState("");
  const [missing, setMissing] = useState(false);
  const chosen = ready.find((document) => document.id === documentId);

  function add() {
    if (chosen === undefined || passage.trim() === "") {
      setMissing(true);
      return;
    }
    onAdd({ document_id: chosen.id, document_name: chosen.name, passage: passage.trim() });
  }

  return (
    <div role="group" aria-labelledby={groupId} className="flex flex-col gap-3 rounded-xl border border-line p-3.5">
      <p id={groupId} className={field.label}>
        Pick a passage
      </p>
      {documents.isError && <Notice tone="error">The Documents could not be loaded. Try again shortly.</Notice>}
      {documents.data !== undefined && ready.length === 0 && (
        <p className={text.muted}>This Project has no Ready Documents yet. Upload one in Documents first.</p>
      )}
      {ready.length > 0 && (
        <label className={field.label}>
          Document
          <select
            className={field.select}
            value={documentId}
            onChange={(event) => {
              setDocumentId(event.target.value);
            }}
          >
            <option value="">Choose a Document</option>
            {ready.map((document) => (
              <option key={document.id} value={document.id}>
                {document.name}
              </option>
            ))}
          </select>
        </label>
      )}
      {chosen !== undefined && (
        <ChunkChoices
          key={chosen.id}
          organisationId={organisationId}
          projectId={projectId}
          documentId={chosen.id}
          onChoose={(chunk) => {
            setPassage(chunk);
            setMissing(false);
          }}
        />
      )}
      <div>
        <label className={field.label}>
          Passage
          <textarea
            className={field.textarea}
            rows={3}
            maxLength={PASSAGE_MAX}
            aria-invalid={missing}
            aria-describedby={missing ? `${hintId} ${errorId}` : hintId}
            value={passage}
            onChange={(event) => {
              setPassage(event.target.value);
            }}
          />
        </label>
        <p id={hintId} className={field.hint}>
          Up to 1,000 characters of one Chunk. A good answer retrieves and cites the Chunk that holds it.
        </p>
        {missing && (
          <p id={errorId} className={field.error}>
            Choose a Document and a passage of it.
          </p>
        )}
      </div>
      <div className="flex gap-2">
        <button type="button" className={button.secondary} onClick={add}>
          Add passage
        </button>
        <button type="button" className={button.quiet} onClick={onCancel}>
          Cancel picking
        </button>
      </div>
    </div>
  );
}

/** The case editor's Expected sources: each with its Document, passage and Remove; Stale ones flagged. */
export function ExpectedSourceList({ sources, onRemove }: { sources: ChosenSource[]; onRemove: (index: number) => void }) {
  if (sources.length === 0) return <p className={text.muted}>No Expected sources.</p>;
  return (
    <ul aria-label="Expected sources" className="flex flex-col gap-2">
      {sources.map((source, index) => (
        <li key={index} className="flex items-start justify-between gap-3 rounded-xl bg-sunken px-3.5 py-2.5 text-sm">
          <span className="flex min-w-0 flex-col gap-1">
            <span className="inline-flex flex-wrap items-center gap-1.5 font-medium text-ink">
              {source.document_name}
              {source.stale === true && <StaleBadge title={staleReason(source)} />}
            </span>
            <span className="whitespace-pre-wrap text-ink-2">“{source.passage}”</span>
            {source.stale === true && <span className={text.muted}>{staleReason(source)}</span>}
          </span>
          <button
            type="button"
            className={button.quiet}
            aria-label={`Remove the passage of ${source.document_name}`}
            onClick={() => {
              onRemove(index);
            }}
          >
            Remove
          </button>
        </li>
      ))}
    </ul>
  );
}

/** A case's expectations as the set and Run detail show them: Expected sources, the Reference answer, Expect Fallback Text. */
export function ExpectationSummary({
  sources,
  referenceAnswer,
  expectFallback,
}: {
  sources: Pick<ChosenSource, "document_name" | "passage" | "stale" | "stale_reason">[];
  referenceAnswer: string | null;
  expectFallback: boolean;
}) {
  return (
    <>
      {referenceAnswer}
      {expectFallback && <span className="block">Expects the Fallback Text.</span>}
      {sources.length > 0 && (
        <ul aria-label="Expected sources" className="flex flex-col gap-1">
          {sources.map((source, index) => (
            <li key={index}>
              <span className="font-medium text-ink">{source.document_name}: </span>
              <span>“{source.passage}”</span>
              {source.stale === true && (
                <span className="ml-1.5 inline-flex">
                  <StaleBadge title={staleReason(source)} />
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
