import type { Schemas } from "@studio/api-client";

import { Diff } from "../design";
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

/** One side of a line diff, as text: the lines before the change, or after it. */
function sideText(lines: DiffLine[], side: "before" | "after"): string {
  const dropped = side === "before" ? "insert" : "delete";
  return lines
    .filter((line) => line.op !== dropped)
    .map((line) => line.text)
    .join("\n");
}

/** A markdown change (a system prompt, Project Instructions) as the design system's line `Diff`. */
function LinesDiff({ lines, label }: { lines: DiffLine[]; label: string }) {
  return <Diff label={label} before={sideText(lines, "before")} after={sideText(lines, "after")} />;
}

function Change({ change, names }: { change: FieldChange; names: Record<string, string> }) {
  const name = settingName(change.path);
  let detail;
  if (change.lines) {
    detail = <LinesDiff lines={change.lines} label={`${name} changes`} />;
  } else if (change.added && change.removed) {
    detail = (
      <p className="text-sm">
        {change.added.length > 0 && <span className="mr-3 text-accent-ink">Added: {shown(change.added, names)}</span>}
        {change.removed.length > 0 && <span className="mr-3 text-danger">Removed: {shown(change.removed, names)}</span>}
        {change.added.length === 0 && change.removed.length === 0 && <span>Reordered</span>}
      </p>
    );
  } else {
    detail = (
      <p className="text-sm">
        <del className="text-danger">{shown(change.before, names)}</del> → <ins className="text-accent-ink no-underline">{shown(change.after, names)}</ins>
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
    return <p className="text-sm text-muted">No differences: {side(diff.from)} and {side(diff.to)} have the same settings.</p>;
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
          <LinesDiff lines={pinned.lines} label="Project Instructions changes" />
        </div>
      )}
    </div>
  );
}
