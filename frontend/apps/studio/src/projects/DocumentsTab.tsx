import { useParams } from "@tanstack/react-router";
import { type ChangeEvent, type DragEvent, useState } from "react";

import {
  canReplace,
  type DocumentStatus,
  type ProjectDocument,
  type Upload,
  useDeleteDocument,
  useDocuments,
  useUploads,
} from "./documents";
import { useProject } from "./projects";
import { useOrganisationRole } from "./ProjectsPage";

/** The file types the API accepts, for the file picker. */
const ACCEPT = ".pdf,.docx,.pptx,.html,.htm,.md,.markdown,.txt";

const STATUS_LABELS: Record<DocumentStatus, string> = {
  queued: "Queued",
  processing: "Processing",
  ready: "Ready",
  failed: "Failed",
};

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${String(bytes)} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function UploadRow({ upload }: { upload: Upload }) {
  const { state } = upload;
  return (
    <li className="flex flex-wrap items-center gap-3 text-sm">
      <span className="font-medium">{upload.name}</span>
      {upload.replacing && <span className="text-slate-700">New edition of {upload.replacing}</span>}
      {state.phase === "uploading" && (
        <progress aria-label={`Uploading ${upload.name}`} max={100} value={state.progress} className="h-2 w-40" />
      )}
      {state.phase === "uploaded" && <span className="text-slate-700">Uploaded</span>}
      {state.phase === "failed" && (
        <span role="alert" className="text-red-700">
          {state.message}
          {state.existing && (
            <>
              {" "}
              <a href={`#document-${state.existing.id}`} className="font-medium underline">
                Show {state.existing.name}
              </a>
            </>
          )}
        </span>
      )}
    </li>
  );
}

function Dropzone({ onFiles }: { onFiles: (files: File[]) => void }) {
  const [dragging, setDragging] = useState(false);

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    onFiles([...event.dataTransfer.files]);
  }

  function onChange(event: ChangeEvent<HTMLInputElement>) {
    // A file input always has a file list; it is only null on other input types.
    onFiles([...(event.target.files as FileList)]);
    event.target.value = "";
  }

  return (
    <div
      data-testid="dropzone"
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => {
        setDragging(false);
      }}
      onDrop={onDrop}
      className={`rounded border-2 border-dashed p-6 text-center ${dragging ? "border-slate-700 bg-slate-50" : "border-slate-300"}`}
    >
      <label className="cursor-pointer font-medium text-slate-900 underline">
        Choose files to upload
        <input type="file" multiple accept={ACCEPT} onChange={onChange} className="sr-only" />
      </label>
      <p className="mt-1 text-sm text-slate-700">or drop them here. PDF, DOCX, PPTX, HTML, Markdown and TXT.</p>
    </div>
  );
}

function ReplacementStatus({ document }: { document: ProjectDocument }) {
  const { replacement } = document;
  if (!replacement) return null;
  return (
    <span className="block text-slate-700">
      New edition {replacement.edition} ({replacement.name}): {STATUS_LABELS[replacement.status]}
      {replacement.error_message && <span className="block text-red-700">{replacement.error_message}</span>}
    </span>
  );
}

function DocumentActions({
  document,
  onReplace,
  onDelete,
}: {
  document: ProjectDocument;
  onReplace: (document: ProjectDocument, file: File) => void;
  onDelete: (document: ProjectDocument) => Promise<void>;
}) {
  const [confirming, setConfirming] = useState(false);
  const [failed, setFailed] = useState(false);

  async function confirmDelete() {
    try {
      await onDelete(document);
    } catch {
      setFailed(true);
      setConfirming(false);
    }
  }

  function onChange(event: ChangeEvent<HTMLInputElement>) {
    const [file] = event.target.files as FileList;
    event.target.value = "";
    if (file) onReplace(document, file);
  }

  if (confirming) {
    return (
      <div role="group" aria-label={`Delete ${document.name}?`} className="flex flex-wrap items-center gap-2">
        <span>Delete {document.name}? It stops being retrieved at once.</span>
        <button type="button" onClick={() => void confirmDelete()} className="rounded bg-red-700 px-2 py-1 text-white">
          Delete
        </button>
        <button
          type="button"
          onClick={() => {
            setConfirming(false);
          }}
          className="underline"
        >
          Cancel
        </button>
      </div>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-3">
      {canReplace(document) && (
        <label className="cursor-pointer underline">
          New edition
          <span className="sr-only"> of {document.name}</span>
          <input type="file" accept={ACCEPT} onChange={onChange} className="sr-only" />
        </label>
      )}
      <button
        type="button"
        aria-label={`Delete ${document.name}`}
        onClick={() => {
          setFailed(false);
          setConfirming(true);
        }}
        className="text-red-700 underline"
      >
        Delete
      </button>
      {failed && (
        <span role="alert" className="text-red-700">
          The Document could not be deleted. Try again.
        </span>
      )}
    </div>
  );
}

function DocumentRows({
  documents,
  editable,
  onReplace,
  onDelete,
}: {
  documents: ProjectDocument[];
  editable: boolean;
  onReplace: (document: ProjectDocument, file: File) => void;
  onDelete: (document: ProjectDocument) => Promise<void>;
}) {
  return (
    <table className="w-full text-left text-sm">
      <caption className="sr-only">Documents</caption>
      <thead>
        <tr className="border-b border-slate-200">
          <th scope="col" className="py-2">
            Name
          </th>
          <th scope="col">Status</th>
          <th scope="col">Chunks</th>
          <th scope="col">Size</th>
          {editable && <th scope="col">Actions</th>}
        </tr>
      </thead>
      <tbody>
        {documents.map((document) => (
          <tr key={document.id} id={`document-${document.id}`} className="border-b border-slate-100 target:bg-amber-50">
            <td className="py-2">{document.name}</td>
            <td>
              {STATUS_LABELS[document.status]}
              {document.error_message && <span className="block text-red-700">{document.error_message}</span>}
              <ReplacementStatus document={document} />
            </td>
            <td>{document.chunk_count}</td>
            <td>{formatSize(document.size_bytes)}</td>
            {editable && (
              <td>
                <DocumentActions document={document} onReplace={onReplace} onDelete={onDelete} />
              </td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/**
 * The Project's Knowledge Base: upload files, and watch each Document go from Queued to Ready.
 * Upload a new edition of a Document to replace it in place, or delete it.
 */
export function DocumentsTab() {
  const { organisationId } = useOrganisationRole();
  const { projectId } = useParams({ from: "/signed-in/organisations/$organisationId/projects/$projectId" });
  const project = useProject(organisationId, projectId);
  const documents = useDocuments(organisationId, projectId);
  const { uploads, upload, replace } = useUploads(organisationId, projectId);
  const deleteDocument = useDeleteDocument(organisationId, projectId);
  const archived = project.data?.archived_at != null;

  let list;
  if (documents.isError) {
    list = <p role="alert">The Documents could not be loaded. Try again shortly.</p>;
  } else if (documents.data === undefined) {
    list = <p role="status">Loading Documents…</p>;
  } else if (documents.data.length === 0) {
    list = <p className="text-slate-700">No Documents yet. Upload files to build this Project's Knowledge Base.</p>;
  } else {
    list = (
      <DocumentRows
        documents={documents.data}
        editable={!archived}
        onReplace={replace}
        onDelete={async (document) => {
          await deleteDocument.mutateAsync(document.id);
        }}
      />
    );
  }

  return (
    <section aria-labelledby="tab-heading" className="space-y-4">
      <h2 id="tab-heading" className="text-lg font-semibold">
        Documents
      </h2>
      {!archived && <Dropzone onFiles={upload} />}
      {uploads.length > 0 && (
        <ul aria-label="Uploads" className="space-y-2">
          {uploads.map((item) => (
            <UploadRow key={item.key} upload={item} />
          ))}
        </ul>
      )}
      {list}
    </section>
  );
}
