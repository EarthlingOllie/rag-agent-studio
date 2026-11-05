import { useParams } from "@tanstack/react-router";
import { type ChangeEvent, type DragEvent, type SubmitEvent, useState } from "react";

import {
  type DocumentFilters,
  type DocumentStatus,
  NO_FILTERS,
  type ProjectDocument,
  type Upload,
  useDocuments,
  useUploads,
} from "./documents";
import { useProject } from "./projects";
import { useOrganisationRole } from "./ProjectsPage";
import { type Tag, tagFailure, useTagChange, useTags } from "./tags";
import { TagsPanel } from "./TagsPanel";

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

const BUTTON = "rounded border border-slate-300 px-2 py-1 text-sm";
const PRIMARY = "rounded bg-slate-900 px-3 py-1 text-sm font-medium text-white disabled:opacity-50";

interface TagScope {
  organisationId: string;
  projectId: string;
  tags: Tag[];
}

function TagList({ document }: { document: ProjectDocument }) {
  if (document.tags.length === 0) return null;
  return (
    <ul aria-label="Tags" className="flex flex-wrap gap-1">
      {document.tags.map((tag) => (
        <li key={tag.id} className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-900">
          {tag.name}
        </li>
      ))}
    </ul>
  );
}

/** Choose exactly which Tags one Document carries. */
function DocumentTagsEditor({ document, scope, onClose }: { document: ProjectDocument; scope: TagScope; onClose: () => void }) {
  const [chosen, setChosen] = useState(() => new Set(document.tags.map((tag) => tag.id)));
  const change = useTagChange(scope.organisationId, scope.projectId);
  const message = tagFailure(change.error);

  function toggle(tagId: string) {
    setChosen((current) => {
      const next = new Set(current);
      if (!next.delete(tagId)) next.add(tagId);
      return next;
    });
  }

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const tagIds = scope.tags.map((tag) => tag.id).filter((id) => chosen.has(id));
    change.mutate({ kind: "set", documentId: document.id, tagIds }, { onSuccess: onClose });
  }

  return (
    <form onSubmit={onSubmit} className="mt-2">
      <fieldset aria-label={`Tags for ${document.name}`} className="space-y-2">
        <div className="flex flex-wrap gap-3">
          {scope.tags.length === 0 && <p className="text-slate-700">This Project has no Tags yet. Add one under Tags.</p>}
          {scope.tags.map((tag) => (
            <label key={tag.id} className="flex items-center gap-1">
              <input
                type="checkbox"
                checked={chosen.has(tag.id)}
                onChange={() => {
                  toggle(tag.id);
                }}
              />
              {tag.name}
            </label>
          ))}
        </div>
        <div className="flex gap-2">
          <button type="submit" className={PRIMARY}>
            Save Tags
          </button>
          <button type="button" className={BUTTON} onClick={onClose}>
            Cancel
          </button>
        </div>
        {message && (
          <p role="alert" className="text-red-700">
            {message}
          </p>
        )}
      </fieldset>
    </form>
  );
}

/** Apply a Tag to, or take it off, every selected Document. */
function BulkTagging({ selected, scope, onClear }: { selected: string[]; scope: TagScope; onClear: () => void }) {
  const [tagId, setTagId] = useState("");
  const change = useTagChange(scope.organisationId, scope.projectId);
  const message = tagFailure(change.error);

  return (
    <fieldset aria-label="Bulk tagging" className="flex flex-wrap items-end gap-2 rounded border border-slate-200 p-3 text-sm">
      <span className="font-medium">{selected.length} selected</span>
      <label className="flex flex-col">
        Tag
        <select
          value={tagId}
          onChange={(event) => {
            setTagId(event.target.value);
          }}
          className="rounded border border-slate-300 px-2 py-1"
        >
          <option value="">Choose a Tag</option>
          {scope.tags.map((tag) => (
            <option key={tag.id} value={tag.id}>
              {tag.name}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        className={PRIMARY}
        disabled={tagId === ""}
        onClick={() => {
          change.mutate({ kind: "bulk", documentIds: selected, action: "add", tagId });
        }}
      >
        Apply to selected
      </button>
      <button
        type="button"
        className={BUTTON}
        disabled={tagId === ""}
        onClick={() => {
          change.mutate({ kind: "bulk", documentIds: selected, action: "remove", tagId });
        }}
      >
        Remove from selected
      </button>
      <button type="button" className={BUTTON} onClick={onClear}>
        Clear selection
      </button>
      {message && (
        <p role="alert" className="w-full text-red-700">
          {message}
        </p>
      )}
    </fieldset>
  );
}

function DocumentRows({
  documents,
  scope,
  editable,
  selected,
  onSelect,
}: {
  documents: ProjectDocument[];
  scope: TagScope;
  editable: boolean;
  selected: Set<string>;
  onSelect: (ids: string[], on: boolean) => void;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const allSelected = documents.every((document) => selected.has(document.id));
  return (
    <table className="w-full text-left text-sm">
      <caption className="sr-only">Documents</caption>
      <thead>
        <tr className="border-b border-slate-200">
          <th scope="col" className="w-8">
            <span className="sr-only">Select</span>
            {editable && (
              <input
                type="checkbox"
                aria-label="Select all Documents"
                checked={allSelected}
                onChange={() => {
                  onSelect(
                    documents.map((document) => document.id),
                    !allSelected,
                  );
                }}
              />
            )}
          </th>
          <th scope="col" className="py-2">
            Name
          </th>
          <th scope="col">Status</th>
          <th scope="col">Tags</th>
          <th scope="col">Chunks</th>
          <th scope="col">Size</th>
        </tr>
      </thead>
      <tbody>
        {documents.map((document) => (
          <tr key={document.id} className="border-b border-slate-100 align-top">
            <td className="py-2">
              {editable && (
                <input
                  type="checkbox"
                  aria-label={`Select ${document.name}`}
                  checked={selected.has(document.id)}
                  onChange={(event) => {
                    onSelect([document.id], event.target.checked);
                  }}
                />
              )}
            </td>
            <td className="py-2">{document.name}</td>
            <td>
              {STATUS_LABELS[document.status]}
              {document.error_message && <span className="block text-red-700">{document.error_message}</span>}
            </td>
            <td>
              <TagList document={document} />
              {editable && editing !== document.id && (
                <button
                  type="button"
                  className="mt-1 text-sm underline"
                  aria-label={`Edit Tags for ${document.name}`}
                  onClick={() => {
                    setEditing(document.id);
                  }}
                >
                  Edit Tags
                </button>
              )}
              {editing === document.id && (
                <DocumentTagsEditor
                  document={document}
                  scope={scope}
                  onClose={() => {
                    setEditing(null);
                  }}
                />
              )}
            </td>
            <td>{document.chunk_count}</td>
            <td>{formatSize(document.size_bytes)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Search by name and filter by status and Tag. */
function Filters({ filters, tags, onChange }: { filters: DocumentFilters; tags: Tag[]; onChange: (filters: DocumentFilters) => void }) {
  const filtered = filters.q !== "" || filters.status !== "" || filters.tagId !== "";
  return (
    <div role="search" className="flex flex-wrap items-end gap-3 text-sm">
      <label className="flex flex-col">
        Search by name
        <input
          type="search"
          value={filters.q}
          onChange={(event) => {
            onChange({ ...filters, q: event.target.value });
          }}
          className="rounded border border-slate-300 px-2 py-1"
        />
      </label>
      <label className="flex flex-col">
        Status
        <select
          value={filters.status}
          onChange={(event) => {
            onChange({ ...filters, status: event.target.value as DocumentStatus | "" });
          }}
          className="rounded border border-slate-300 px-2 py-1"
        >
          <option value="">Any status</option>
          {Object.entries(STATUS_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col">
        Filter by Tag
        <select
          value={filters.tagId}
          onChange={(event) => {
            onChange({ ...filters, tagId: event.target.value });
          }}
          className="rounded border border-slate-300 px-2 py-1"
        >
          <option value="">Any Tag</option>
          {tags.map((tag) => (
            <option key={tag.id} value={tag.id}>
              {tag.name}
            </option>
          ))}
        </select>
      </label>
      {filtered && (
        <button
          type="button"
          className={BUTTON}
          onClick={() => {
            onChange(NO_FILTERS);
          }}
        >
          Clear filters
        </button>
      )}
    </div>
  );
}

/** The Project's Knowledge Base: upload files, and watch each Document go from Queued to Ready. */
export function DocumentsTab() {
  const { organisationId } = useOrganisationRole();
  const { projectId } = useParams({ from: "/signed-in/organisations/$organisationId/projects/$projectId" });
  const project = useProject(organisationId, projectId);
  const [filters, setFilters] = useState<DocumentFilters>(NO_FILTERS);
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const documents = useDocuments(organisationId, projectId, filters);
  const tags = useTags(organisationId, projectId);
  const { uploads, upload } = useUploads(organisationId, projectId);
  const archived = project.data?.archived_at != null;
  const editable = project.data !== undefined && !archived;
  const scope = { organisationId, projectId, tags: tags.data ?? [] };
  const filtered = filters !== NO_FILTERS;
  // Only Documents still in the list can stay selected.
  const listed = new Set((documents.data ?? []).map((document) => document.id));
  const chosen = [...selected].filter((id) => listed.has(id));

  function select(ids: string[], on: boolean) {
    setSelected((current) => {
      const next = new Set(current);
      for (const id of ids) {
        if (on) next.add(id);
        else next.delete(id);
      }
      return next;
    });
  }

  let list;
  if (documents.isError) {
    list = <p role="alert">The Documents could not be loaded. Try again shortly.</p>;
  } else if (documents.data === undefined) {
    list = <p role="status">Loading Documents…</p>;
  } else if (documents.data.length === 0) {
    list = filtered ? (
      <p className="text-slate-700">No Documents match these filters.</p>
    ) : (
      <p className="text-slate-700">No Documents yet. Upload files to build this Project's Knowledge Base.</p>
    );
  } else {
    list = (
      <DocumentRows documents={documents.data} scope={scope} editable={editable} selected={new Set(chosen)} onSelect={select} />
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
      <TagsPanel organisationId={organisationId} projectId={projectId} editable={editable} />
      <Filters filters={filters} tags={scope.tags} onChange={setFilters} />
      {chosen.length > 0 && (
        <BulkTagging
          selected={chosen}
          scope={scope}
          onClear={() => {
            setSelected(new Set());
          }}
        />
      )}
      {list}
    </section>
  );
}
