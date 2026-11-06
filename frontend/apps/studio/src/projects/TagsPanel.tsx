import { type SubmitEvent, useState } from "react";

import { type Tag, tagFailure, useTagChange, useTags } from "./tags";

const BUTTON = "rounded border border-slate-300 px-2 py-1 text-sm";
const PRIMARY = "rounded bg-slate-900 px-3 py-1 text-sm font-medium text-white";

function documentCount(count: number): string {
  return count === 1 ? "1 Document" : `${String(count)} Documents`;
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
        onSuccess: () => {
          setName("");
        },
      },
    );
  }

  const message = blank ? "Give the Tag a name." : tagFailure(create.error);
  return (
    <form onSubmit={onSubmit} className="flex flex-wrap items-end gap-2">
      <label className="flex flex-col text-sm">
        New Tag
        <input
          value={name}
          maxLength={50}
          onChange={(event) => {
            setName(event.target.value);
          }}
          className="rounded border border-slate-300 px-2 py-1"
        />
      </label>
      <button type="submit" className={PRIMARY} disabled={create.isPending}>
        Add Tag
      </button>
      {message && (
        <p role="alert" className="w-full text-sm text-red-700">
          {message}
        </p>
      )}
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
        <form onSubmit={rename} className="flex flex-wrap items-center gap-2">
          <input
            aria-label={`Name for ${tag.name}`}
            value={name}
            required
            maxLength={50}
            onChange={(event) => {
              setName(event.target.value);
            }}
            className="rounded border border-slate-300 px-2 py-1 text-sm"
          />
          <button type="submit" className={PRIMARY}>
            Save
          </button>
          <button
            type="button"
            className={BUTTON}
            onClick={() => {
              change.reset();
              setMode("view");
            }}
          >
            Cancel
          </button>
          {message && (
            <p role="alert" className="w-full text-sm text-red-700">
              {message}
            </p>
          )}
        </form>
      </li>
    );
  }

  return (
    <li className="flex flex-wrap items-center gap-2 text-sm">
      <span data-testid="tag-name" className="font-medium">
        {tag.name}
      </span>
      <span className="text-slate-700">
        {documentCount(tag.document_count)}
      </span>
      {editable && mode === "view" && (
        <>
          <button
            type="button"
            className={BUTTON}
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
            className={BUTTON}
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
        <span className="flex flex-wrap items-center gap-2">
          <span>
            Delete {tag.name}? It is taken off{" "}
            {documentCount(tag.document_count)}. The Documents stay.
          </span>
          <button
            type="button"
            className="rounded bg-red-700 px-2 py-1 text-white"
            onClick={() => {
              change.mutate({ kind: "delete", tagId: tag.id }, done);
            }}
          >
            Delete Tag
          </button>
          <button
            type="button"
            className={BUTTON}
            onClick={() => {
              setMode("view");
            }}
          >
            Keep it
          </button>
        </span>
      )}
      {message && (
        <span role="alert" className="w-full text-red-700">
          {message}
        </span>
      )}
    </li>
  );
}

/** The Project's Tags: create, rename and delete them. Read-only while the Project is archived. */
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
    list = <p role="alert">The Tags could not be loaded. Try again shortly.</p>;
  } else if (tags.data === undefined) {
    list = <p role="status">Loading Tags…</p>;
  } else if (tags.data.length === 0) {
    list = (
      <p className="text-sm text-slate-700">
        No Tags yet. Tags organise Documents by topic or audience.
      </p>
    );
  } else {
    list = (
      <ul className="space-y-1">
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
    <section
      aria-labelledby="tags-heading"
      className="space-y-2 rounded border border-slate-200 p-4"
    >
      <h3 id="tags-heading" className="font-semibold">
        Tags
      </h3>
      {list}
      {editable && (
        <NewTag organisationId={organisationId} projectId={projectId} />
      )}
    </section>
  );
}
