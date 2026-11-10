import type { Schemas } from "@studio/api-client";

import { Diff } from "../design";
import type { AgentDiff } from "./agents";

type FieldChange = Schemas["FieldChangeOut"];
type DiffLine = Schemas["DiffLineOut"];
type JsonValue = FieldChange["before"];
export type RetrievalMode = Schemas["RetrievalMode"];

const RETRIEVAL_MODES: Record<RetrievalMode, string> = { automatic: "Automatic", agentic: "Agentic" };

/** A Retrieval Mode as Editors read it: "Automatic" or "Agentic". */
export const retrievalModeName = (mode: RetrievalMode) => RETRIEVAL_MODES[mode];

/** The Retrieval Mode row of a Version Diff: both Versions' modes, or the one they share. */
function ModesRow({ modes }: { modes: { from: RetrievalMode; to: RetrievalMode } }) {
  const [from, to] = [retrievalModeName(modes.from), retrievalModeName(modes.to)];
  return <p className="text-sm font-medium">{from === to ? `Retrieval Mode: ${from} in both` : `Retrieval Mode: ${from} → ${to}`}</p>;
}

const GROUPS: Record<string, string> = {
  behaviour: "Behaviour",
  retrieval: "Retrieval",
  experience: "Experience",
  guardrails: "Guardrails",
};

/** Settings whose name isn't their place in the AgentConfig, by their path. */
const SETTING_NAMES: Record<string, string> = {
  "retrieval.mode": "Retrieval › Retrieval mode",
};

/** Values that read better as words, by the path of their setting. */
const VALUE_NAMES: Record<string, Record<string, string>> = {
  "retrieval.mode": { automatic: "Automatic", agentic: "Agentic" },
};

/** "retrieval.tag_ids" → "Retrieval › Tag ids". */
export function settingName(path: string): string {
  const named = SETTING_NAMES[path];
  if (named) return named;
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

function Change({ change, names: given }: { change: FieldChange; names: Record<string, string> }) {
  const name = settingName(change.path);
  const names = { ...given, ...VALUE_NAMES[change.path] };
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
 * Versions, the change of pinned Project Instructions. `names` turns IDs (Tags) into names. A
 * Version Diff given both Versions' `modes` shows the Retrieval Mode first, changed or not.
 */
export function AgentDiffView({
  diff,
  names = {},
  modes,
}: {
  diff: AgentDiff;
  names?: Record<string, string>;
  modes?: { from: RetrievalMode; to: RetrievalMode } | undefined;
}) {
  const title = `Changes from ${side(diff.from)} to ${side(diff.to)}`;
  const pinned = diff.instructions;
  // The Retrieval Mode row says it, so the change isn't listed twice.
  const changes = modes ? diff.changes.filter((change) => change.path !== "retrieval.mode") : diff.changes;
  const modesRow = modes && <ModesRow modes={modes} />;
  if (changes.length === 0 && !pinned) {
    return (
      <div className="space-y-3">
        {modesRow}
        <p className="text-sm text-muted">No differences: {side(diff.from)} and {side(diff.to)} have the same settings.</p>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      {modesRow}
      {changes.length > 0 && (
        <ul aria-label={title} className="space-y-2">
          {changes.map((change) => (
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
