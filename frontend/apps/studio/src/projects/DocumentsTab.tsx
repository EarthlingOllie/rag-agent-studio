import { useParams } from "@tanstack/react-router";
import { type ChangeEvent, type DragEvent, useState } from "react";

import {
  type DocumentStatus,
  type FailureCategory,
  type ProjectDocument,
  type Upload,
  type UploadLimits,
  useDocuments,
  useRetryDocument,
  useUploadLimits,
  useUploads,
} from "./documents";
import { ProjectRequestError, useProject } from "./projects";
import { useOrganisationRole } from "./ProjectsPage";

/** The file types the API accepts, for the file picker, until the upload limits have loaded. */
const ACCEPT = [".pdf", ".docx", ".pptx", ".html", ".htm", ".md", ".markdown", ".txt"];

const STATUS_LABELS: Record<DocumentStatus, string> = {
  queued: "Queued",
  processing: "Processing",
  ready: "Ready",
  failed: "Failed",
};

const CATEGORY_LABELS: Record<FailureCategory, string> = {
  unsupported_content: "Unsupported content",
  conversion: "Conversion error",
  provider: "Provider error",
  quota: "Quota reached",
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
      {state.phase === "uploading" && (
        <progress aria-label={`Uploading ${upload.name}`} max={100} value={state.progress} className="h-2 w-40" />
      )}
      {state.phase === "uploaded" && <span className="text-slate-700">Uploaded</span>}
      {state.phase === "failed" && (
        <span role="alert" className="text-red-700">
          {state.message}
        </span>
      )}
    </li>
  );
}

function Dropzone({ onFiles, limits }: { onFiles: (files: File[]) => void; limits: UploadLimits | undefined }) {
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
        <input type="file" multiple accept={(limits?.accepted_extensions ?? ACCEPT).join(",")} onChange={onChange} className="sr-only" />
      </label>
      <p className="mt-1 text-sm text-slate-700">
        or drop them here. PDF, DOCX, PPTX, HTML, Markdown and TXT
        {limits && `, up to ${formatSize(limits.max_upload_bytes)} each`}.
      </p>
    </div>
  );
}

function StatusCell({ document, onRetry, retrying }: { document: ProjectDocument; onRetry: () => void; retrying: boolean }) {
  const failed = document.status === "failed";
  return (
    <td>
      {STATUS_LABELS[document.status]}
      {failed && document.error_category && <span className="block font-medium text-red-700">{CATEGORY_LABELS[document.error_category]}</span>}
      {document.error_message && <span className={`block ${failed ? "text-red-700" : "text-slate-700"}`}>{document.error_message}</span>}
      {failed && (
        <button
          type="button"
          onClick={onRetry}
          disabled={retrying}
          aria-label={`Retry ${document.name}`}
          className="mt-1 rounded border border-slate-400 px-2 py-0.5 text-slate-900 disabled:opacity-50"
        >
          Retry
        </button>
      )}
    </td>
  );
}

function DocumentRows({
  documents,
  onRetry,
  retrying,
}: {
  documents: ProjectDocument[];
  onRetry: (documentId: string) => void;
  retrying: string | undefined;
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
        </tr>
      </thead>
      <tbody>
        {documents.map((document) => (
          <tr key={document.id} className="border-b border-slate-100">
            <td className="py-2">{document.name}</td>
            <StatusCell
              document={document}
              retrying={retrying === document.id}
              onRetry={() => {
                onRetry(document.id);
              }}
            />
            <td>{document.chunk_count}</td>
            <td>{formatSize(document.size_bytes)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** The Project's Knowledge Base: upload files, and watch each Document go from Queued to Ready. */
export function DocumentsTab() {
  const { organisationId } = useOrganisationRole();
  const { projectId } = useParams({ from: "/signed-in/organisations/$organisationId/projects/$projectId" });
  const project = useProject(organisationId, projectId);
  const documents = useDocuments(organisationId, projectId);
  const limits = useUploadLimits(organisationId, projectId);
  const { uploads, upload } = useUploads(organisationId, projectId, limits.data);
  const retry = useRetryDocument(organisationId, projectId);
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
        onRetry={(documentId) => {
          retry.mutate(documentId);
        }}
        retrying={retry.isPending ? retry.variables : undefined}
      />
    );
  }

  return (
    <section aria-labelledby="tab-heading" className="space-y-4">
      <h2 id="tab-heading" className="text-lg font-semibold">
        Documents
      </h2>
      {limits.data && (
        <p className="text-sm text-slate-700">
          {limits.data.documents_counted} of {limits.data.document_quota} Documents in this Project&apos;s quota. Failed Documents don&apos;t
          count.
        </p>
      )}
      {retry.isError && (
        <p role="alert" className="text-red-700">
          {retry.error instanceof ProjectRequestError && retry.error.status === 409 && retry.error.detail
            ? retry.error.detail
            : "The Document couldn't be retried. Try again."}
        </p>
      )}
      {!archived && <Dropzone onFiles={upload} limits={limits.data} />}
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
