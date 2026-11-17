import { Link } from "@tanstack/react-router";
import { type SubmitEvent, useId, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { Diff, Dialog, EmptyState, Notice, PageHeader, Skeleton, Status, button, field, surface, text } from "../design";
import { formatTime } from "../settings/AuditPage";
import type { Agent } from "./agents";
import { evaluationFailure } from "./evaluation";
import { dollars } from "./format";
import {
  defaultRange,
  type EvidenceCount,
  type Suggestion,
  type SuggestionEstimate,
  type SuggestionEvidence,
  type SuggestionRange,
  type SuggestionSummary,
  suggestionInProgress,
  useCancelSuggestionRun,
  useStartSuggestionRun,
  useSuggestion,
  useSuggestionEstimate,
  useSuggestionEvidence,
  useSuggestions,
} from "./suggestions";

type AgentPath = { organisation_id: string; project_id: string; agent_id: string };

const STATUS = {
  queued: { tone: "working", label: "Queued" },
  gathering: { tone: "working", label: "Gathering evidence" },
  proposing: { tone: "working", label: "Proposing" },
  checking: { tone: "working", label: "Checking" },
  completed: { tone: "ready", label: "Completed" },
  failed: { tone: "failed", label: "Failed" },
  cancelled: { tone: "flagged", label: "Cancelled" },
} as const;

const OUTCOMES = {
  changes: "Changes suggested",
  gaps_only: "No configuration change",
  no_change: "No change suggested",
} as const;

/** What each setting a Suggestion may change is called. */
const SETTINGS: Record<string, string> = {
  "behaviour.system_prompt": "System prompt",
  "retrieval.top_k": "Top-k",
  "retrieval.minimum_score": "Minimum Score",
  "retrieval.hybrid_weighting": "Hybrid weighting",
};

const settingName = (path: string) => SETTINGS[path] as string;
const day = (iso: string) => iso.slice(0, 10);
const rangeText = (suggestion: SuggestionSummary) => `${suggestion.range_start} to ${suggestion.range_end} (UTC)`;

/** The most evidence a run reads: the most recent pieces. */
const EVIDENCE_MAX = 50;

const count = (n: number, one: string, many: string) => `${String(n)} ${n === 1 ? one : many}`;

/** What a finished run spent proposing, for the list. */
function spentText(suggestion: SuggestionSummary): string | null {
  if (suggestionInProgress(suggestion)) return null;
  const spent = suggestion.cost.proposing_usd;
  return spent === null ? "Cost unknown" : `Cost ${dollars(spent)}`;
}

/** A Suggestion's Cost: what proposing spent against its estimate, and the check's estimate. */
function costText(suggestion: SuggestionSummary): string {
  const { proposing_usd: spent, estimated_proposing_usd: proposing, estimated_checking_usd: checking } = suggestion.cost;
  const estimate = proposing === null ? "no estimate" : `estimated ${dollars(proposing)}`;
  const check = checking === null ? "Not checked." : `Checking estimated at ${dollars(checking)}.`;
  return `Proposing cost ${spent === null ? "unknown" : dollars(spent)} (${estimate}). ${check}`;
}

function SuggestionStatus({ suggestion }: { suggestion: SuggestionSummary }) {
  const status = STATUS[suggestion.status];
  return <Status tone={status.tone}>{status.label}</Status>;
}

/** The Agent's Suggestions, newest first, with their state, range and outcome; choosing one shows it below. */
function SuggestionList({
  suggestions,
  chosen,
  onChoose,
}: {
  suggestions: SuggestionSummary[];
  chosen: string | null;
  onChoose: (suggestionId: string) => void;
}) {
  return (
    <ul aria-label="Suggestion runs" className={`${surface.card} divide-y divide-line-soft`}>
      {suggestions.map((suggestion) => (
        <li
          key={suggestion.id}
          className={`flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3 text-sm ${suggestion.id === chosen ? "bg-accent-soft" : ""}`}
        >
          <button
            type="button"
            className={button.quiet}
            aria-current={suggestion.id === chosen ? "true" : undefined}
            onClick={() => {
              onChoose(suggestion.id);
            }}
          >
            Suggestion of {formatTime(suggestion.created_at)}
          </button>
          <SuggestionStatus suggestion={suggestion} />
          <span className="text-ink-2">{rangeText(suggestion)}</span>
          <span className="text-ink-2">From Version {suggestion.base_version_number}</span>
          {suggestion.outcome !== null && <span className="font-medium text-ink-2">{OUTCOMES[suggestion.outcome]}</span>}
          {spentText(suggestion) !== null && <span className="font-mono text-xs text-muted">{spentText(suggestion)}</span>}
        </li>
      ))}
    </ul>
  );
}

const CHIP = "inline-flex items-center rounded-full border border-line bg-surface px-2.5 py-0.5 text-xs text-ink-2 hover:text-accent";

/** What a piece of evidence is, in words: purged text, its Live Verdict and each reason it counts; or its Evaluation Case. */
function evidenceWords(evidence: SuggestionEvidence): string[] {
  if (evidence.run_case_id !== null) return [evidence.case_deleted ? "Case deleted" : "Evaluation Case failed"];
  const words: string[] = [];
  if (evidence.text_purged) words.push("Text purged");
  if (evidence.live_verdict !== null) words.push(evidence.live_verdict === "fail" ? "Live Verdict failed" : "Live Verdict passed");
  if (evidence.kinds.includes("thumbs_down")) words.push("Thumbs-down");
  if (evidence.kinds.includes("low_rating")) words.push("Rated 1 or 2");
  return words;
}

/**
 * A piece of evidence: a reply opens in the Agent's Conversations viewer, an Evaluation Case opens
 * its result in Run detail. Purged text and deleted cases say so.
 */
function EvidenceChip({ evidence, path }: { evidence: SuggestionEvidence; path: AgentPath }) {
  const label = [evidence.label, day(evidence.occurred_at), ...evidenceWords(evidence)].join(" · ");
  const params = { organisationId: path.organisation_id, projectId: path.project_id, agentId: path.agent_id };
  if (evidence.run_case_id !== null) {
    return (
      <Link
        to="/organisations/$organisationId/projects/$projectId/agents/$agentId/evaluation"
        params={params}
        search={{ run: evidence.evaluation_run_id as string, case: evidence.run_case_id }}
        className={CHIP}
      >
        {label}
      </Link>
    );
  }
  return (
    <Link
      to="/organisations/$organisationId/projects/$projectId/agents/$agentId/conversations/$conversationId"
      params={{
        organisationId: path.organisation_id,
        projectId: path.project_id,
        agentId: path.agent_id,
        conversationId: evidence.conversation_id as string,
      }}
      hash={`message-${evidence.message_id as string}`}
      className={CHIP}
    >
      {label}
    </Link>
  );
}

function EvidenceChips({ label, evidence, path }: { label: string; evidence: SuggestionEvidence[]; path: AgentPath }) {
  return (
    <ul aria-label={label} className="flex flex-wrap gap-2">
      {evidence.map((each) => (
        <li key={each.id}>
          <EvidenceChip evidence={each} path={path} />
        </li>
      ))}
    </ul>
  );
}

function ChangeRow({ suggestion, index, path }: { suggestion: Suggestion; index: number; path: AgentPath }) {
  const change = suggestion.changes[index] as Suggestion["changes"][number];
  const name = settingName(change.path);
  const cited = suggestion.evidence.filter((each) => change.evidence_ids.includes(each.id));
  return (
    <li className={`${surface.panel} flex flex-col gap-3`}>
      <h4 className="font-medium text-ink">{name}</h4>
      <Diff label={`Suggested change to the ${name.toLowerCase()}`} before={String(change.base_value)} after={String(change.suggested_value)} />
      <p className="text-sm text-ink-2">{change.explanation}</p>
      {cited.length > 0 && <EvidenceChips label={`Evidence for the ${name.toLowerCase()} change`} evidence={cited} path={path} />}
    </li>
  );
}

/** The Knowledge Base gaps a Suggestion found, each with its evidence, and a link to the Project's Knowledge Base. */
function GapList({ suggestion, path }: { suggestion: Suggestion; path: AgentPath }) {
  return (
    <div className="flex flex-col gap-2">
      <h4 className="font-medium text-ink">Knowledge Base gaps</h4>
      <p className="text-sm text-muted">
        Topics the failed replies asked about that no Chunk covered. No configuration change fixes these: add Documents that cover them.{" "}
        <Link
          to="/organisations/$organisationId/projects/$projectId"
          params={{ organisationId: path.organisation_id, projectId: path.project_id }}
          className="font-medium text-accent hover:underline"
        >
          Open the Knowledge Base
        </Link>
      </p>
      <ul aria-label="Knowledge Base gaps" className="flex flex-col gap-3">
        {suggestion.gaps.map((gap) => {
          const cited = suggestion.evidence.filter((each) => gap.evidence_ids.includes(each.id));
          return (
            <li key={gap.id} className={`${surface.panel} flex flex-col gap-2`}>
              <h5 className="font-medium text-ink">{gap.topic}</h5>
              <p className="text-sm text-ink-2">{gap.explanation}</p>
              {cited.length > 0 && <EvidenceChips label={`Evidence for the gap ${gap.topic}`} evidence={cited} path={path} />}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** A Suggestion: its explanation, each change as a Diff with its evidence, its Knowledge Base gaps, and all its evidence. Polled while in progress. */
function SuggestionDetail({ path, suggestionId }: { path: AgentPath; suggestionId: string }) {
  const read = useSuggestion(path, suggestionId);
  const cancel = useCancelSuggestionRun(path);
  const headingId = useId();
  if (read.isPending) return <Skeleton label="Loading the Suggestion" />;
  if (read.isError) return <Notice tone="error">The Suggestion could not be loaded. Try again shortly.</Notice>;
  const suggestion = read.data;
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <h3 id={headingId} className={text.heading}>
          Suggestion of {formatTime(suggestion.created_at)}
        </h3>
        <SuggestionStatus suggestion={suggestion} />
      </div>
      <p className={text.muted}>
        {`From Version ${String(suggestion.base_version_number)}'s replies, ${rangeText(suggestion)}. Proposed by ${suggestion.model_provider}:${suggestion.model_name}.`}
      </p>
      <p className="font-mono text-xs text-muted">{costText(suggestion)}</p>
      {suggestionInProgress(suggestion) && (
        <div className="flex flex-wrap items-center gap-3">
          <p role="status" className="text-sm text-ink-2">
            {`${STATUS[suggestion.status].label}…`}
          </p>
          <button
            type="button"
            className={button.secondary}
            disabled={cancel.isPending}
            onClick={() => {
              cancel.mutate(suggestion.id);
            }}
          >
            Cancel run
          </button>
        </div>
      )}
      {cancel.isError && <Notice tone="error">{evaluationFailure(cancel.error)}</Notice>}
      {suggestion.status === "cancelled" && <Notice tone="info">This run was cancelled. It stopped before its next phase and keeps what it spent.</Notice>}
      {suggestion.status === "failed" && <Notice tone="error">{suggestion.error_message}</Notice>}
      {suggestion.explanation !== null && <p className="text-[15px] text-ink">{suggestion.explanation}</p>}
      {suggestion.outcome === "no_change" && <p className="text-sm font-medium text-ink-2">No change suggested.</p>}
      {suggestion.outcome === "gaps_only" && <p className="text-sm font-medium text-ink-2">No configuration change.</p>}
      {suggestion.changes.length > 0 && (
        <ul aria-label="Suggested changes" className="flex flex-col gap-3">
          {suggestion.changes.map((change, index) => (
            <ChangeRow key={change.id} suggestion={suggestion} index={index} path={path} />
          ))}
        </ul>
      )}
      {suggestion.gaps.length > 0 && <GapList suggestion={suggestion} path={path} />}
      {suggestion.evidence.length > 0 && (
        <div className="flex flex-col gap-2">
          <h4 className="font-medium text-ink">Evidence</h4>
          <p className="text-sm text-muted">
            {`${String(suggestion.evidence.length)} of ${String(suggestion.evidence_total)} pieces of evidence in the range, the most recent first. A reply opens in the Conversations viewer, an Evaluation Case in Run detail.`}
          </p>
          <EvidenceChips label="Evidence" evidence={suggestion.evidence} path={path} />
        </div>
      )}
    </section>
  );
}

/** How much evidence the dialog's range holds, by kind, with a warning when it is too little to be more than noise. */
function EvidenceInRange({ path, range }: { path: AgentPath; range: SuggestionRange | null }) {
  const counted = useSuggestionEvidence(path, range);
  let figure: string;
  let found: EvidenceCount | undefined;
  if (range === null) {
    figure = "Choose a range to count its evidence.";
  } else if (counted.isError) {
    figure = `The evidence could not be counted. ${evaluationFailure(counted.error) as string}`;
  } else if (counted.data === undefined) {
    figure = "Counting the evidence…";
  } else {
    found = counted.data;
    const kinds = [
      count(found.live_verdict, "failed Live Verdict", "failed Live Verdicts"),
      `${String(found.thumbs_down)} thumbs-down`,
      `${String(found.low_rating)} rated 1 or 2`,
      count(found.evaluation_case, "failed Evaluation Case", "failed Evaluation Cases"),
    ].join(", ");
    const capped = found.total > EVIDENCE_MAX ? `. A run reads the ${String(EVIDENCE_MAX)} most recent.` : "";
    figure = `${count(found.total, "piece", "pieces")} of evidence: ${kinds}${capped}`;
  }
  return (
    <div className="flex flex-col gap-2">
      <p className={field.label}>Evidence</p>
      <p role="status" aria-label="Evidence in the range" className="text-sm text-ink">
        {figure}
      </p>
      {found?.likely_noise && <Notice tone="warning">Fewer than 10 pieces of evidence: the Suggestion is likely to be noise. You can still start it.</Notice>}
    </div>
  );
}

function estimateText(estimate: SuggestionEstimate): string {
  const { total_usd: total, proposing_usd: proposing, checking_usd: checking } = estimate;
  if (total === null || proposing === null) return "The Cost can't be estimated: a model this run uses has no price set.";
  if (checking === null) return `About ${dollars(total)}: proposing ${dollars(proposing)}. Not checked: this Agent has no Evaluation Set.`;
  return `About ${dollars(total)}: proposing ${dollars(proposing)}, checking against the Evaluation Set ${dollars(checking)}`;
}

/** The estimated Cost of a Suggestion run of the dialog's range, proposing and checking. */
function SuggestionEstimatedCost({ path, range }: { path: AgentPath; range: SuggestionRange | null }) {
  const estimate = useSuggestionEstimate(path, range);
  let figure: string;
  if (range === null) figure = "Choose a range to see the estimated Cost.";
  else if (estimate.isError) figure = `The Cost could not be estimated. ${evaluationFailure(estimate.error) as string}`;
  else if (estimate.data === undefined) figure = "Estimating the Cost…";
  else figure = estimateText(estimate.data);
  return (
    <div>
      <p className={field.label}>Estimated Cost</p>
      <p role="status" aria-label="Estimated Cost" className="mt-1 text-sm text-ink">
        {figure}
      </p>
      <p className={field.hint}>
        Proposing is priced at the Evaluation Model&apos;s prices for each piece of evidence it reads and for its answer; checking, at the Evaluation Run estimate for the Live Version and the Suggestion. The run records what it actually costs. The Evaluation budget never applies.
      </p>
    </div>
  );
}

/** The Suggestion run dialog: the range of UTC days to read (the last 14 by default), its evidence by kind and the estimated Cost. */
function SuggestDialog({ path, onStarted, onClose }: { path: AgentPath; onStarted: (suggestionId: string) => void; onClose: () => void }) {
  const formId = useId();
  const start = useStartSuggestionRun(path);
  const [range, setRange] = useState(() => defaultRange(new Date()));
  const backwards = range.range_start > range.range_end;
  const counted = range.range_start !== "" && range.range_end !== "" && !backwards ? range : null;

  function submit(event: SubmitEvent) {
    event.preventDefault();
    start.mutate(range, {
      onSuccess: (suggestion) => {
        onStarted(suggestion.id);
      },
    });
  }

  return (
    <Dialog
      open
      title="Suggest changes"
      description="The Evaluation Model reads the Live Version's replies in the range that failed their Live Verdict, got a thumbs-down or are in a Conversation rated 1 or 2, and the Evaluation Cases it failed in its latest Run, then proposes system prompt and retrieval changes and lists Knowledge Base gaps. Nothing changes until an Editor applies it."
      onClose={onClose}
      closeButton={false}
      footer={
        <>
          <button type="button" className={button.secondary} onClick={onClose}>
            Cancel
          </button>
          <button type="submit" form={formId} className={button.primary} disabled={backwards || start.isPending}>
            Start Suggestion run
          </button>
        </>
      }
    >
      <form id={formId} aria-label="Suggest changes" className="flex flex-col gap-4" onSubmit={submit}>
        <FormError message={evaluationFailure(start.error) ?? (backwards ? "The range must start on or before the day it ends." : undefined)} />
        <label className={field.label}>
          From (UTC day)
          <input
            type="date"
            className={field.input}
            value={range.range_start}
            required
            onChange={(event) => {
              setRange({ ...range, range_start: event.target.value });
            }}
          />
        </label>
        <label className={field.label}>
          To (UTC day)
          <input
            type="date"
            className={field.input}
            value={range.range_end}
            required
            onChange={(event) => {
              setRange({ ...range, range_end: event.target.value });
            }}
          />
        </label>
        <EvidenceInRange path={path} range={counted} />
        <SuggestionEstimatedCost path={path} range={counted} />
      </form>
    </Dialog>
  );
}

/**
 * The Evaluation view's Suggestions tab: the Agent's Suggestion runs, "Suggest changes" for an
 * active, published Agent, and the chosen Suggestion's detail. An archived Agent's are read only.
 */
export function AgentSuggestions({ agent, organisationId }: { agent: Agent; organisationId: string }) {
  const path = { organisation_id: organisationId, project_id: agent.project_id, agent_id: agent.id };
  const headingId = useId();
  const suggestions = useSuggestions(path);
  const [chosen, setChosen] = useState<string | null>(null);
  const [suggesting, setSuggesting] = useState(false);
  const archived = agent.archived_at !== null;
  const published = agent.live_version !== null;
  const running = (suggestions.data ?? []).some(suggestionInProgress);
  const shown = chosen ?? suggestions.data?.[0]?.id ?? null;

  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-4">
      <PageHeader
        level={2}
        headingId={headingId}
        title="Suggestions"
        description="Proposed changes to this Agent's configuration, drawn from its Live Version's failed replies and Evaluation Cases. A Suggestion never changes the Draft by itself."
        actions={
          !archived && (
            <button
              type="button"
              className={button.primary}
              disabled={!published || running}
              onClick={() => {
                setSuggesting(true);
              }}
            >
              {running ? "Suggesting…" : "Suggest changes"}
            </button>
          )
        }
      />
      {archived && <Notice tone="info">This Agent is archived: its Suggestions are read only, and it starts no Suggestion run.</Notice>}
      {!archived && !published && <Notice tone="info">Publish this Agent first: a Suggestion is made from its Live Version&apos;s replies.</Notice>}
      {suggestions.isPending && <Skeleton label="Loading the Suggestions" />}
      {suggestions.isError && <EmptyState tone="error" icon="agents" level={3} title="The Suggestions could not be loaded" description="Try again shortly." />}
      {suggestions.data && suggestions.data.length === 0 && (
        <EmptyState
          icon="agents"
          level={3}
          title="No Suggestions yet"
          description="Suggest changes to have the Evaluation Model read the Live Version's failures and propose a fix."
        />
      )}
      {suggestions.data && suggestions.data.length > 0 && <SuggestionList suggestions={suggestions.data} chosen={shown} onChoose={setChosen} />}
      {shown !== null && <SuggestionDetail key={shown} path={path} suggestionId={shown} />}
      {suggesting && (
        <SuggestDialog
          path={path}
          onStarted={(suggestionId) => {
            setSuggesting(false);
            setChosen(suggestionId);
          }}
          onClose={() => {
            setSuggesting(false);
          }}
        />
      )}
    </section>
  );
}
