import { type SubmitEvent, useState } from "react";

import { button, field, Notice, Skeleton } from "../design";
import { type Tag, tagFailure, useTagChange, useTags } from "./tags";

function documentCount(count: number): string {
  return count === 1 ? "1 Document" : `${String(count)} Documents`;
}

/** Deleting a Tag takes it out of the Drafts scoped to it, which widens what they search. */
function scopedAgentsWarning(tag: Tag): string | undefined {
  const count = tag.agents.length;
  if (count === 0) return undefined;
  const agents = count === 1 ? "1 Agent is" : `${String(count)} Agents are`;
  const names = tag.agents.map((agent) => agent.name).join(", ");
  return `${agents} limited to ${tag.name}: ${names}. Deleting it takes it out of their Drafts; an Agent left with no Tags searches every Document.`;
}

function NewTag({
  organisationId,
  projectId,
}: {
  organisationId: string;
  projectId: string;
}) {
  const [name, setName] = useState("");
  const [blank, setBlank] = useState(false);
  const create = useTagChange(organisationId, projectId);

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = name.trim();
    setBlank(trimmed === "");
    if (trimmed === "") return;
    create.mutate(
      { kind: "create", name: trimmed },
      {
        // Clears the field only if it still holds the name just added: a name typed while
        // the request was in flight is kept.
        onSuccess: () => {
          setName((current) => (current.trim() === trimmed ? "" : current));
        },
      },
    );
  }

  const message = blank ? "Give the Tag a name." : tagFailure(create.error);
  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-2 border-t border-line-soft pt-4">
      <div className="flex items-end gap-2">
        <label className={`${field.label} flex-1`}>
          New Tag
          <input
            value={name}
            maxLength={50}
            onChange={(event) => {
              setName(event.target.value);
            }}
            className={field.input}
          />
        </label>
        <button type="submit" className={button.secondary} disabled={create.isPending}>
          Add Tag
        </button>
      </div>
      {message && <Notice tone="error">{message}</Notice>}
    </form>
  );
}

function TagRow({
  tag,
  organisationId,
  projectId,
  editable,
}: {
  tag: Tag;
  organisationId: string;
  projectId: string;
  editable: boolean;
}) {
  const [mode, setMode] = useState<"view" | "rename" | "delete">("view");
  const [name, setName] = useState(tag.name);
  const change = useTagChange(organisationId, projectId);
  const message = tagFailure(change.error);
  const warning = scopedAgentsWarning(tag);
  const done = {
    onSuccess: () => {
      setMode("view");
    },
  };

  function rename(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    change.mutate({ kind: "rename", tagId: tag.id, name: name.trim() }, done);
  }

  if (mode === "rename") {
    return (
      <li>
        <form onSubmit={rename} className="flex flex-wrap items-center gap-2 py-2">
          <input
            aria-label={`Name for ${tag.name}`}
            value={name}
            required
            maxLength={50}
            onChange={(event) => {
              setName(event.target.value);
            }}
            className={`${field.input} mt-0 w-auto flex-1`}
          />
          <button type="submit" className={button.secondary}>
            Save
          </button>
          <button
            type="button"
            className={button.ghost}
            onClick={() => {
              change.reset();
              setMode("view");
            }}
          >
            Cancel
          </button>
          {message && (
            <div className="w-full">
              <Notice tone="error">{message}</Notice>
            </div>
          )}
        </form>
      </li>
    );
  }

  return (
    <li className="flex flex-wrap items-center gap-2 py-2 text-sm">
      <span data-testid="tag-name" className="inline-flex rounded-full bg-sand px-2.5 py-0.5 text-xs text-sand-ink">
        {tag.name}
      </span>
      <span className="mr-auto text-muted">
        {documentCount(tag.document_count)}
      </span>
      {editable && mode === "view" && (
        <>
          <button
            type="button"
            className={button.quiet}
            aria-label={`Rename ${tag.name}`}
            onClick={() => {
              setName(tag.name);
              setMode("rename");
            }}
          >
            Rename
          </button>
          <button
            type="button"
            className={`${button.quiet} text-danger hover:text-danger`}
            aria-label={`Delete ${tag.name}`}
            onClick={() => {
              setMode("delete");
            }}
          >
            Delete
          </button>
        </>
      )}
      {mode === "delete" && (
        <span className="flex w-full flex-wrap items-center gap-2 rounded-xl bg-sunken p-3">
          <span className="w-full text-ink">
            Delete {tag.name}? It is taken off{" "}
            {documentCount(tag.document_count)}. The Documents stay.
          </span>
          {warning && (
            <span role="alert" className="w-full text-flag">
              {warning}
            </span>
          )}
          <button
            type="button"
            className={button.dangerFilled}
            onClick={() => {
              change.mutate({ kind: "delete", tagId: tag.id }, done);
            }}
          >
            Delete Tag
          </button>
          <button
            type="button"
            className={button.secondary}
            onClick={() => {
              setMode("view");
            }}
          >
            Keep it
          </button>
        </span>
      )}
      {message && (
        <span role="alert" className="w-full text-danger">
          {message}
        </span>
      )}
    </li>
  );
}

/**
 * The Project's Tags: create, rename and delete them. Read-only while the Project is archived.
 * Opened from Manage tags on the Documents toolbar, inside the "Tags" dialog.
 */
export function TagsPanel({
  organisationId,
  projectId,
  editable,
}: {
  organisationId: string;
  projectId: string;
  editable: boolean;
}) {
  const tags = useTags(organisationId, projectId);

  let list;
  if (tags.isError) {
    list = <Notice tone="error">The Tags could not be loaded. Try again shortly.</Notice>;
  } else if (tags.data === undefined) {
    list = <Skeleton label="Loading Tags" lines={2} />;
  } else if (tags.data.length === 0) {
    list = <p className="text-sm text-muted">No Tags yet.</p>;
  } else {
    list = (
      <ul aria-label="Tags" className="flex flex-col divide-y divide-line-soft">
        {tags.data.map((tag) => (
          <TagRow
            key={tag.id}
            tag={tag}
            organisationId={organisationId}
            projectId={projectId}
            editable={editable}
          />
        ))}
      </ul>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {list}
      {editable && (
        <NewTag organisationId={organisationId} projectId={projectId} />
      )}
    </div>
  );
}
