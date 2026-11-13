import { Link, useParams } from "@tanstack/react-router";
import { type ChangeEvent, type DragEvent, type ReactNode, type Ref, type SubmitEvent, useRef, useState } from "react";

import {
  BulkBar,
  button,
  ConfirmDialog,
  Dialog,
  EmptyState,
  field,
  FlagCount,
  Icon,
  layout,
  Menu,
  type MenuItem,
  Notice,
  Segmented,
  Skeleton,
  StatCard,
  Status,
  surface,
  table,
  Tag as TagPill,
  ToastProvider,
  useToast,
} from "../design";
import {
  canReplace,
  type DocumentFilters,
  type DocumentStatus,
  type FailureCategory,
  NO_FILTERS,
  type ProjectDocument,
  quotaMessage,
  retryFailure,
  type Upload,
  type UploadLimits,
  useDeleteDocument,
  useDocuments,
  useRetryDocument,
  useUploadLimits,
  useUploads,
} from "./documents";
import { type Project, useProject } from "./projects";
import { useOrganisationRole } from "./ProjectsPage";
import { type Tag, tagFailure, useTagChange, useTags } from "./tags";
import { TagsPanel } from "./TagsPanel";

/** The file types the API accepts, for the file picker, until the upload limits have loaded. */
const ACCEPT = [".pdf", ".docx", ".pptx", ".html", ".htm", ".md", ".markdown", ".txt"];

function accept(limits: UploadLimits | undefined): string {
  return (limits?.accepted_extensions ?? ACCEPT).join(",");
}

export const STATUS_LABELS: Record<DocumentStatus, string> = {
  queued: "Queued",
  processing: "Processing",
  ready: "Ready",
  failed: "Failed",
};

/** The dot beside each status: green when Ready, grey while it is worked on, red when it failed. */
export const STATUS_TONES: Record<DocumentStatus, "ready" | "working" | "failed"> = {
  queued: "working",
  processing: "working",
  ready: "ready",
  failed: "failed",
};

const CATEGORY_LABELS: Record<FailureCategory, string> = {
  unsupported_content: "Unsupported content",
  conversion: "Conversion error",
  provider: "Provider error",
  quota: "Quota reached",
};

/** How the Studio names a Document's file type, from its extension. */
const FILE_TYPES: Record<string, string> = {
  pdf: "PDF",
  docx: "DOCX",
  pptx: "PPTX",
  html: "HTML",
  htm: "HTML",
  md: "Markdown",
  markdown: "Markdown",
  txt: "Text",
};

/** A Document's file type, from its extension: "PDF", "Markdown"; "File" for one the Studio doesn't name. */
export function fileType(name: string): string {
  return FILE_TYPES[name.slice(name.lastIndexOf(".") + 1).toLowerCase()] ?? "File";
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${String(bytes)} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function plural(count: number, one: string, many: string): string {
  return `${String(count)} ${count === 1 ? one : many}`;
}

/** What deleting a Document does to what Agents can retrieve. */
function deletionConsequence(chunks: number): string {
  if (chunks === 0) return "It has no chunks, so no Agent retrieves it.";
  return `Its ${plural(chunks, "chunk", "chunks")} ${chunks === 1 ? "stops" : "stop"} being retrieved at once.`;
}

function UploadRow({ upload }: { upload: Upload }) {
  const { state } = upload;
  return (
    <li className="flex flex-col gap-2 text-sm">
      <span className="flex flex-wrap items-center gap-3">
        <span className="font-medium text-ink">{upload.name}</span>
        {upload.replacing && <span className="text-muted">New edition of {upload.replacing}</span>}
        {state.phase === "uploading" && (
          <progress
            aria-label={`Uploading ${upload.name}`}
            max={100}
            value={state.progress}
            className="h-1.5 w-40 accent-accent"
          />
        )}
        {state.phase === "uploaded" && <span className="text-muted">Uploaded</span>}
      </span>
      {state.phase === "failed" && (
        <Notice tone="error">
          {state.message}
          {state.existing && (
            <>
              {" "}
              <a href={`#document-${state.existing.id}`} className="font-medium underline">
                Show {state.existing.name}
              </a>
            </>
          )}
        </Notice>
      )}
    </li>
  );
}

/**
 * A file input, used by Upload (inside its button-shaped label, `sr-only`) and by each row's New
 * edition (`hidden`, opened from the ⋯ menu, and named by `label`).
 */
function FilePicker({
  label,
  multiple = false,
  limits,
  onFiles,
  inputRef,
  className,
}: {
  label?: string;
  multiple?: boolean;
  limits: UploadLimits | undefined;
  onFiles: (files: File[]) => void;
  inputRef?: Ref<HTMLInputElement>;
  className: string;
}) {
  function onChange(event: ChangeEvent<HTMLInputElement>) {
    // A file input always has a file list; it is only null on other input types.
    const files = [...(event.target.files as FileList)];
    event.target.value = "";
    onFiles(files);
  }
  return (
    <input
      ref={inputRef}
      type="file"
      multiple={multiple}
      accept={accept(limits)}
      aria-label={label}
      onChange={onChange}
      className={className}
    />
  );
}

/** The quiet drop target under the toolbar; Upload in the toolbar is the picker. */
function Dropzone({ onFiles, limits }: { onFiles: (files: File[]) => void; limits: UploadLimits | undefined }) {
  const [dragging, setDragging] = useState(false);

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    onFiles([...event.dataTransfer.files]);
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
      className={`${surface.dropzone} ${dragging ? "border-accent bg-accent-soft text-accent-ink" : ""}`}
    >
      <span className="inline-flex items-center gap-2">
        <Icon name="upload" size={16} />
        Drop files here to upload. PDF, DOCX, PPTX, HTML, Markdown and TXT
        {limits && `, up to ${formatSize(limits.max_upload_bytes)} each`}.
      </span>
    </div>
  );
}

/** Why a Document, or its new edition, failed: the category and the readable message. */
function Failure({ status, category, message }: { status: DocumentStatus; category: FailureCategory | null; message: string | null }) {
  const failed = status === "failed";
  return (
    <>
      {failed && category && <span className="mt-1 block text-xs font-medium text-danger">{CATEGORY_LABELS[category]}</span>}
      {message && <span className={`mt-0.5 block text-xs ${failed ? "text-danger" : "text-muted"}`}>{message}</span>}
    </>
  );
}

function ReplacementStatus({ document }: { document: ProjectDocument }) {
  const { replacement } = document;
  if (!replacement) return null;
  return (
    <span className="mt-1 block text-xs text-muted">
      New edition {replacement.edition} ({replacement.name}): {STATUS_LABELS[replacement.status]}
      <Failure status={replacement.status} category={replacement.error_category} message={replacement.error_message} />
    </span>
  );
}

interface TagScope {
  organisationId: string;
  projectId: string;
  tags: Tag[];
}

/** What a row's ⋯ menu asks the page to do. */
interface RowActions {
  onRetry: (document: ProjectDocument) => void;
  onReplace: (document: ProjectDocument, file: File) => void;
  onEditTags: (document: ProjectDocument) => void;
  onDelete: (document: ProjectDocument) => void;
}

/** Retry and New edition (once the Document is Ready or Failed), Edit Tags and Delete. */
function RowMenu({
  document,
  limits,
  retrying,
  actions,
}: {
  document: ProjectDocument;
  limits: UploadLimits | undefined;
  retrying: boolean;
  actions: RowActions;
}) {
  const picker = useRef<HTMLInputElement>(null);
  const settled = canReplace(document);
  const items: MenuItem[] = [
    ...(settled
      ? [
          // Reprocesses the Document with the Project's current settings, such as OCR.
          { label: "Retry", icon: "history" as const, disabled: retrying, onSelect: () => { actions.onRetry(document); } },
          { label: "New edition", icon: "upload" as const, onSelect: () => picker.current?.click() },
        ]
      : []),
    { label: "Edit Tags", onSelect: () => { actions.onEditTags(document); } },
    { label: "Delete", icon: "trash", danger: true, onSelect: () => { actions.onDelete(document); } },
  ];
  return (
    <>
      <Menu
        label={<Icon name="more" />}
        triggerLabel={`More actions for ${document.name}`}
        menuLabel={`Actions for ${document.name}`}
        align="end"
        triggerClassName={button.iconBare}
        items={items}
      />
      {settled && (
        <FilePicker
          label={`New edition of ${document.name}`}
          className="hidden"
          limits={limits}
          inputRef={picker}
          onFiles={([file]) => {
            if (file) actions.onReplace(document, file);
          }}
        />
      )}
    </>
  );
}

function TagList({ document }: { document: ProjectDocument }) {
  if (document.tags.length === 0) return <span className="text-muted">—</span>;
  return (
    <ul aria-label="Tags" className="flex flex-wrap gap-1">
      {document.tags.map((tag) => (
        <li key={tag.id} className="contents">
          <TagPill>{tag.name}</TagPill>
        </li>
      ))}
    </ul>
  );
}

/** Choose exactly which Tags one Document carries, in a dialog from the row's ⋯ menu. */
function DocumentTagsDialog({
  document,
  scope,
  onSaved,
  onClose,
}: {
  document: ProjectDocument;
  scope: TagScope;
  onSaved: () => void;
  onClose: () => void;
}) {
  const [chosen, setChosen] = useState(() => new Set(document.tags.map((tag) => tag.id)));
  const change = useTagChange(scope.organisationId, scope.projectId);
  const message = tagFailure(change.error);
  const formId = `tags-for-${document.id}`;

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
    change.mutate({ kind: "set", documentId: document.id, tagIds }, { onSuccess: onSaved });
  }

  return (
    <Dialog
      open
      title={`Tags for ${document.name}`}
      onClose={onClose}
      footer={
        <>
          <button type="button" className={button.secondary} onClick={onClose}>
            Cancel
          </button>
          <button type="submit" form={formId} className={button.primary} disabled={change.isPending}>
            Save Tags
          </button>
        </>
      }
    >
      <form id={formId} onSubmit={onSubmit} className="flex flex-col gap-3">
        <fieldset aria-label={`Tags for ${document.name}`} className="flex flex-wrap gap-x-4 gap-y-2 text-sm text-ink">
          {scope.tags.length === 0 && <p className="text-muted">This Project has no Tags yet. Add one under Manage tags.</p>}
          {scope.tags.map((tag) => (
            <label key={tag.id} className="flex items-center gap-2">
              <input
                type="checkbox"
                className={field.checkbox}
                checked={chosen.has(tag.id)}
                onChange={() => {
                  toggle(tag.id);
                }}
              />
              {tag.name}
            </label>
          ))}
        </fieldset>
        {message && <Notice tone="error">{message}</Notice>}
      </form>
    </Dialog>
  );
}

/** Add a Tag to, or take it off, every selected Document, from the bulk bar. */
function BulkTagging({
  selected,
  scope,
  onClear,
}: {
  selected: string[];
  scope: TagScope;
  onClear: () => void;
}) {
  const change = useTagChange(scope.organisationId, scope.projectId);
  const message = tagFailure(change.error);
  const toast = useToast();
  const documents = plural(selected.length, "Document", "Documents");

  function tagItems(action: "add" | "remove"): MenuItem[] {
    return scope.tags.map((tag) => ({
      id: tag.id,
      label: tag.name,
      onSelect: () => {
        change.mutate(
          { kind: "bulk", documentIds: selected, action, tagId: tag.id },
          {
            onSuccess: () => {
              toast.show(action === "add" ? `Added ${tag.name} to ${documents}.` : `Removed ${tag.name} from ${documents}.`);
            },
          },
        );
      },
    }));
  }

  const none = scope.tags.length === 0;
  return (
    <div className="flex flex-col gap-2">
      <BulkBar count={selected.length} noun={["Document", "Documents"]} onClear={onClear}>
        <Menu
          label="Add Tag"
          menuLabel="Add a Tag to the selected Documents"
          align="end"
          triggerClassName={button.secondary}
          disabled={none || change.isPending}
          items={tagItems("add")}
        />
        <Menu
          label="Remove Tag"
          menuLabel="Remove a Tag from the selected Documents"
          align="end"
          triggerClassName={button.secondary}
          disabled={none || change.isPending}
          items={tagItems("remove")}
        />
      </BulkBar>
      {message && <Notice tone="error">{message}</Notice>}
    </div>
  );
}

function DocumentRows({
  documents,
  scope,
  editable,
  selected,
  onSelect,
  limits,
  retrying,
  actions,
}: {
  documents: ProjectDocument[];
  scope: TagScope;
  editable: boolean;
  selected: Set<string>;
  onSelect: (ids: string[], on: boolean) => void;
  limits: UploadLimits | undefined;
  retrying: boolean;
  actions: RowActions;
}) {
  const allSelected = documents.every((document) => selected.has(document.id));
  return (
    <div className={table.wrap}>
      <table className={`${table.table} min-w-[820px]`}>
        <caption className="sr-only">Documents</caption>
        <thead>
          <tr>
            <th scope="col" className={`${table.th} w-10`}>
              <span className="sr-only">Select</span>
              {editable && (
                <input
                  type="checkbox"
                  className={field.checkbox}
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
            <th scope="col" className={table.th}>
              Name
            </th>
            <th scope="col" className={table.th}>
              Type
            </th>
            <th scope="col" className={table.th}>
              Tags
            </th>
            <th scope="col" className={table.th}>
              Status
            </th>
            <th scope="col" className={table.thNumeric}>
              Chunks
            </th>
            <th scope="col" className={table.thNumeric}>
              Quarantined
            </th>
            <th scope="col" className={table.thNumeric}>
              Size
            </th>
            <th scope="col" className={`${table.th} w-12`}>
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {documents.map((document) => (
            <tr key={document.id} id={`document-${document.id}`} className={`${table.row} target:bg-flag-soft`}>
              <td className={table.td}>
                {editable && (
                  <input
                    type="checkbox"
                    className={field.checkbox}
                    aria-label={`Select ${document.name}`}
                    checked={selected.has(document.id)}
                    onChange={(event) => {
                      onSelect([document.id], event.target.checked);
                    }}
                  />
                )}
              </td>
              <td className={table.td}>
                <Link
                  to="/organisations/$organisationId/projects/$projectId/documents/$documentId"
                  params={{
                    organisationId: scope.organisationId,
                    projectId: scope.projectId,
                    documentId: document.id,
                  }}
                  className={table.link}
                >
                  {document.name}
                </Link>
              </td>
              <td className={table.tdMuted}>
                <span className="font-mono text-xs">{fileType(document.name)}</span>
              </td>
              <td className={table.td}>
                <TagList document={document} />
              </td>
              <td className={table.td}>
                <Status tone={STATUS_TONES[document.status]}>{STATUS_LABELS[document.status]}</Status>
                <Failure status={document.status} category={document.error_category} message={document.error_message} />
                <ReplacementStatus document={document} />
              </td>
              <td className={table.tdNumeric}>{document.chunk_count}</td>
              <td className={table.tdNumeric}>
                {/* Chunks the ingestion Guardrail scan flagged and nobody has allowed yet: in the flag colour, so
                    Documents waiting for review stand out. */}
                <FlagCount count={document.quarantined_chunk_count} label="quarantined chunks" />
              </td>
              <td className={table.tdNumeric}>{formatSize(document.size_bytes)}</td>
              <td className={table.td}>
                {editable && <RowMenu document={document} limits={limits} retrying={retrying} actions={actions} />}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** The toolbar: search by name, Tag chips, Manage tags, a status filter, and Upload, the one primary action. */
function Toolbar({
  filters,
  tags,
  onChange,
  onManageTags,
  upload,
}: {
  filters: DocumentFilters;
  tags: Tag[];
  onChange: (filters: DocumentFilters) => void;
  onManageTags: () => void;
  upload: ReactNode;
}) {
  const filtered = filters.q !== "" || filters.status !== "" || filters.tagId !== "";
  // A Tag filter left over from a deleted Tag reads as All.
  const tagId = tags.some((tag) => tag.id === filters.tagId) ? filters.tagId : "";
  return (
    <div role="search" className={layout.toolbar}>
      <label className={`${field.search} w-full sm:w-64`}>
        <Icon name="search" size={14} />
        <input
          type="search"
          aria-label="Search by name"
          placeholder="Search Documents"
          value={filters.q}
          onChange={(event) => {
            onChange({ ...filters, q: event.target.value });
          }}
          className="min-w-0 flex-1 bg-transparent text-ink placeholder:text-muted focus:outline-none"
        />
      </label>
      {tags.length > 0 && (
        <Segmented
          label="Filter by Tag"
          options={[{ value: "", label: "All" }, ...tags.map((tag) => ({ value: tag.id, label: tag.name }))]}
          value={tagId}
          onChange={(value) => {
            onChange({ ...filters, tagId: value });
          }}
        />
      )}
      <button type="button" className={button.ghost} onClick={onManageTags}>
        Manage tags
      </button>
      <span className="ml-auto flex flex-wrap items-center gap-3">
        {filtered && (
          <button
            type="button"
            className={button.ghost}
            onClick={() => {
              onChange(NO_FILTERS);
            }}
          >
            Clear filters
          </button>
        )}
        <select
          aria-label="Status"
          value={filters.status}
          onChange={(event) => {
            onChange({ ...filters, status: event.target.value as DocumentStatus | "" });
          }}
          className={field.pill}
        >
          <option value="">Any status</option>
          {Object.entries(STATUS_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        {upload}
      </span>
    </div>
  );
}

/** The Knowledge Base at a glance: Documents against the quota, Chunks, quarantined chunks and the Embedding Model. */
function Stats({ project, documents, limits }: { project: Project; documents: ProjectDocument[] | undefined; limits: UploadLimits | undefined }) {
  const chunks = documents?.reduce((sum, document) => sum + document.chunk_count, 0);
  const quarantined = documents?.reduce((sum, document) => sum + document.quarantined_chunk_count, 0);
  const dash = (value: number | undefined) => (value === undefined ? "—" : value.toLocaleString("en-GB"));
  return (
    <section aria-label="Knowledge Base" className={layout.stats}>
      {limits ? (
        <StatCard label="Documents" value={dash(limits.documents_counted)} unit={`/ ${limits.document_quota.toLocaleString("en-GB")}`} />
      ) : (
        <StatCard label="Documents" value="—" />
      )}
      <StatCard label="Chunks" value={dash(chunks)} />
      <StatCard label="Quarantined chunks" value={dash(quarantined)} tone={quarantined !== undefined && quarantined > 0 ? "flag" : "default"} />
      <StatCard label="Embedding Model" value={<span className="text-base">{project.embedding_model_id}</span>} />
    </section>
  );
}

/**
 * The Project's Knowledge Base: upload files, and watch each Document go from Queued to Ready.
 * Upload a new edition of a Document to replace it in place, or delete it.
 */
function DocumentsSection() {
  const { organisationId } = useOrganisationRole();
  const { projectId } = useParams({
    from: "/signed-in/organisations/$organisationId/projects/$projectId",
  });
  const toast = useToast();
  // The Project frame shows a section only once the Project has loaded.
  const project = useProject(organisationId, projectId);
  const [filters, setFilters] = useState<DocumentFilters>(NO_FILTERS);
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [managingTags, setManagingTags] = useState(false);
  const [editingTags, setEditingTags] = useState<ProjectDocument | null>(null);
  const [deleting, setDeleting] = useState<ProjectDocument | null>(null);
  const documents = useDocuments(organisationId, projectId, filters);
  // The figures are the whole Project's, whatever the filters show.
  const everything = useDocuments(organisationId, projectId);
  const tags = useTags(organisationId, projectId);
  const limits = useUploadLimits(organisationId, projectId);
  const { uploads, upload, replace } = useUploads(organisationId, projectId, limits.data);
  const deleteDocument = useDeleteDocument(organisationId, projectId);
  const retry = useRetryDocument(organisationId, projectId);
  const archived = project.data?.archived_at != null;
  const editable = project.data !== undefined && !archived;
  const scope = { organisationId, projectId, tags: tags.data ?? [] };
  const filtered = filters !== NO_FILTERS;
  // Only Documents still in the list can stay selected.
  const listed = new Set((documents.data ?? []).map((document) => document.id));
  const chosen = [...selected].filter((id) => listed.has(id));
  const failedCount = (everything.data ?? []).filter((document) => document.status === "failed").length;
  const full = limits.data !== undefined && limits.data.documents_counted >= limits.data.document_quota;

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

  const actions: RowActions = {
    onRetry: (document) => {
      retry.mutate(document.id, {
        onSuccess: () => {
          toast.show(`Retrying ${document.name}.`);
        },
      });
    },
    onReplace: replace,
    onEditTags: setEditingTags,
    onDelete: (document) => {
      deleteDocument.reset();
      setDeleting(document);
    },
  };

  let list;
  if (documents.isError) {
    list = <EmptyState tone="error" title="The Documents could not be loaded" description="Try again shortly." />;
  } else if (documents.data === undefined) {
    list = <Skeleton label="Loading Documents" />;
  } else if (documents.data.length === 0) {
    list = filtered ? (
      <EmptyState icon="search" title="No Documents match these filters" description="Clear the filters to see every Document." />
    ) : (
      <EmptyState icon="documents" title="No Documents yet" description="Upload files to build this Project's Knowledge Base." />
    );
  } else {
    list = (
      <DocumentRows
        documents={documents.data}
        scope={scope}
        editable={editable}
        selected={new Set(chosen)}
        onSelect={select}
        limits={limits.data}
        retrying={retry.isPending}
        actions={actions}
      />
    );
  }

  return (
    <section aria-labelledby="tab-heading" className="flex flex-col gap-6">
      <h2 id="tab-heading" className="sr-only">
        Documents
      </h2>
      <Stats project={project.data as Project} documents={everything.data} limits={limits.data} />
      <Toolbar
        filters={filters}
        tags={scope.tags}
        onChange={setFilters}
        onManageTags={() => {
          setManagingTags(true);
        }}
        upload={
          !archived && (
            <label className={`${button.primary} cursor-pointer has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-accent`}>
              <Icon name="upload" size={16} />
              Upload
              <FilePicker multiple limits={limits.data} onFiles={upload} className="sr-only" />
            </label>
          )
        }
      />
      {!archived && <Dropzone onFiles={upload} limits={limits.data} />}
      {full && <Notice tone="warning">{quotaMessage(limits.data.document_quota)}</Notice>}
      {failedCount > 0 && (
        <Notice tone="warning">
          {plural(failedCount, "Document", "Documents")} failed to process.
          {editable && (failedCount === 1 ? " Retry it from its ⋯ menu, or upload a fixed copy." : " Retry each from its ⋯ menu, or upload fixed copies.")}
        </Notice>
      )}
      {uploads.length > 0 && (
        <ul aria-label="Uploads" className={`${surface.panel} flex flex-col gap-3`}>
          {uploads.map((item) => (
            <UploadRow key={item.key} upload={item} />
          ))}
        </ul>
      )}
      {retry.error && <Notice tone="error">{retryFailure(retry.error)}</Notice>}
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
      <Dialog
        open={managingTags}
        title="Tags"
        description="Tags organise Documents by topic or audience."
        onClose={() => {
          setManagingTags(false);
        }}
      >
        <TagsPanel organisationId={organisationId} projectId={projectId} editable={editable} />
      </Dialog>
      {editingTags && (
        <DocumentTagsDialog
          document={editingTags}
          scope={scope}
          onSaved={() => {
            toast.show(`Saved the Tags on ${editingTags.name}.`);
            setEditingTags(null);
          }}
          onClose={() => {
            setEditingTags(null);
          }}
        />
      )}
      {deleting && (
        <ConfirmDialog
          open
          destructive
          title={`Delete ${deleting.name}?`}
          confirmLabel={`Delete ${deleting.name}`}
          busy={deleteDocument.isPending}
          body={deleteDocument.isError ? <Notice tone="error">The Document could not be deleted. Try again.</Notice> : undefined}
          onConfirm={() => {
            deleteDocument.mutate(deleting.id, {
              onSuccess: () => {
                toast.show(`Deleted ${deleting.name}.`);
                setDeleting(null);
              },
            });
          }}
          onCancel={() => {
            setDeleting(null);
          }}
        >
          {deletionConsequence(deleting.chunk_count)}
        </ConfirmDialog>
      )}
    </section>
  );
}

/** The Documents section, with its own toasts (Deleted, Retrying, Tags saved). */
export function DocumentsTab() {
  return (
    <ToastProvider>
      <DocumentsSection />
    </ToastProvider>
  );
}
