import type { Schemas } from "@studio/api-client";

import type { AgentDiff } from "./agents";

type FieldChange = Schemas["FieldChangeOut"];
type DiffLine = Schemas["DiffLineOut"];
type JsonValue = FieldChange["before"];

const GROUPS: Record<string, string> = {
  behaviour: "Behaviour",
  retrieval: "Retrieval",
  experience: "Experience",
  guardrails: "Guardrails",
};

/** "retrieval.tag_ids" → "Retrieval › Tag ids". */
export function settingName(path: string): string {
  return path
    .split(".")
    .map((part, index) => {
      // Every path starts with one of the AgentConfig's four groups.
      if (index === 0) return GROUPS[part] as string;
      const words = part.replaceAll("_", " ");
      return words.charAt(0).toUpperCase() + words.slice(1);
    })
    .join(" › ");
}

/** How a setting's value reads in a diff. */
function shown(value: JsonValue, names: Record<string, string>): string {
  if (value === null) return "(none)";
  if (value === "") return "(empty)";
  if (typeof value === "boolean") return value ? "On" : "Off";
  if (typeof value === "string") return names[value] ?? value;
  // Lists show only the items added or removed, never empty.
  if (Array.isArray(value)) return value.map((item) => shown(item, names)).join(", ");
  if (typeof value === "number") return String(value);
  // The only settings that are objects are model choices, which read as their model.
  return (value as { model: string }).model;
}

const LINE_STYLE: Record<DiffLine["op"], { sign: string; label: string; className: string }> = {
  equal: { sign: " ", label: "Unchanged", className: "text-slate-700" },
  delete: { sign: "−", label: "Removed", className: "bg-red-50 text-red-900" },
  insert: { sign: "+", label: "Added", className: "bg-green-50 text-green-900" },
};

/** A line diff of markdown: removed lines marked −, added lines +. */
export function TextDiff({ lines, label }: { lines: DiffLine[]; label: string }) {
  return (
    <ol aria-label={label} className="overflow-x-auto rounded border border-slate-200 font-mono text-xs">
      {lines.map((line, index) => {
        const style = LINE_STYLE[line.op];
        return (
          <li key={index} className={`whitespace-pre-wrap px-2 ${style.className}`}>
            <span className="sr-only">{style.label}: </span>
            <span aria-hidden="true">{style.sign} </span>
            {line.text}
          </li>
        );
      })}
    </ol>
  );
}

function Change({ change, names }: { change: FieldChange; names: Record<string, string> }) {
  const name = settingName(change.path);
  let detail;
  if (change.lines) {
    detail = <TextDiff lines={change.lines} label={`${name} changes`} />;
  } else if (change.added && change.removed) {
    detail = (
      <p className="text-sm">
        {change.added.length > 0 && <span className="mr-3 text-green-900">Added: {shown(change.added, names)}</span>}
        {change.removed.length > 0 && <span className="mr-3 text-red-900">Removed: {shown(change.removed, names)}</span>}
        {change.added.length === 0 && change.removed.length === 0 && <span>Reordered</span>}
      </p>
    );
  } else {
    detail = (
      <p className="text-sm">
        <del className="text-red-900">{shown(change.before, names)}</del> → <ins className="text-green-900 no-underline">{shown(change.after, names)}</ins>
      </p>
    );
  }
  return (
    <li className="space-y-1">
      <p className="text-sm font-medium">{name}</p>
      {detail}
    </li>
  );
}

const side = (found: Schemas["DiffSideOut"]) => (found.version ? `v${String(found.version.number)}` : "the Draft");

/**
 * Every setting that differs between two sides, with a line diff for markdown and, between two
 * Versions, the change of pinned Project Instructions. `names` turns IDs (Tags) into names.
 */
export function AgentDiffView({ diff, names = {} }: { diff: AgentDiff; names?: Record<string, string> }) {
  const title = `Changes from ${side(diff.from)} to ${side(diff.to)}`;
  const pinned = diff.instructions;
  if (diff.changes.length === 0 && !pinned) {
    return <p className="text-sm text-slate-700">No differences: {side(diff.from)} and {side(diff.to)} have the same settings.</p>;
  }
  return (
    <div className="space-y-3">
      {diff.changes.length > 0 && (
        <ul aria-label={title} className="space-y-2">
          {diff.changes.map((change) => (
            <Change key={change.path} change={change} names={names} />
          ))}
        </ul>
      )}
      {pinned && (
        <div className="space-y-1">
          <p className="text-sm font-medium">
            Project Instructions: {pinned.before ? `v${String(pinned.before.number)}` : "none"} →{" "}
            {pinned.after ? `v${String(pinned.after.number)}` : "none"}
          </p>
          <TextDiff lines={pinned.lines} label="Project Instructions changes" />
        </div>
      )}
    </div>
  );
}
