/** The status badges the Studio shows beside Agents, Versions, Conversations, KPIs and Provider Credentials. */
const BADGES = {
  live: { label: "Live", className: "bg-accent-soft text-accent-ink", dot: "bg-accent" },
  draft: { label: "Draft", className: "bg-sand text-sand-ink" },
  notLive: { label: "Not live", className: "bg-sunken text-muted" },
  archived: { label: "Archived", className: "bg-sunken text-muted" },
  instructionsBehind: { label: "Instructions behind", className: "bg-flag-soft text-flag" },
  budgetSpent: { label: "Budget spent", className: "bg-danger-soft text-danger" },
  blocked: { label: "Blocked by guardrail", className: "bg-danger-soft text-danger" },
  lowSample: { label: "Low sample", className: "bg-flag-soft text-flag" },
  /** A Chunk the ingestion Guardrail scan flagged as possible instructions to an AI. */
  flagged: { label: "Flagged", className: "bg-flag-soft text-flag" },
  /** A Provider Credential whose last check passed. */
  checkPassed: { label: "Working", className: "bg-accent-soft text-accent-ink", dot: "bg-accent" },
  /** A Provider Credential whose last check failed; the reason goes beside it. */
  checkFailed: { label: "Check failed", className: "bg-danger-soft text-danger" },
} as const satisfies Record<string, { label: string; className: string; dot?: string }>;

export type BadgeKind = keyof typeof BADGES;

/** Each badge's words: the same everywhere, so Members learn them once. */
export const BADGE_LABELS = Object.fromEntries(
  Object.entries(BADGES).map(([kind, { label }]) => [kind, label]),
) as Record<BadgeKind, string>;

const PILL = "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium";

/**
 * A small pill. `kind` picks the words and colour (Live, Draft, Not live, Archived, Instructions
 * behind, Budget spent, Blocked by guardrail, Low sample, Flagged, Working, Check failed);
 * `kind="version"` is a Version chip.
 * The words always carry the meaning; colour only repeats it.
 */
export function Badge(props: { kind: BadgeKind; title?: string } | { kind: "version"; version: number }) {
  if (props.kind === "version") {
    return (
      <span aria-label={`Version ${String(props.version)}`} className={`${PILL} border border-line bg-surface font-mono text-ink-2`}>
        v{props.version}
      </span>
    );
  }
  const badge: { label: string; className: string; dot?: string } = BADGES[props.kind];
  return (
    <span title={props.title} className={`${PILL} ${badge.className}`}>
      {badge.dot !== undefined && <span aria-hidden="true" className={`size-1.5 rounded-full ${badge.dot}`} />}
      {badge.label}
    </span>
  );
}
