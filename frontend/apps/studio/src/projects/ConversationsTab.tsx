import { Link, Outlet, useNavigate, useParams, useSearch } from "@tanstack/react-router";
import { createContext, type ReactNode, useContext, useId, useState } from "react";

import { Badge, ConfirmDialog, EmptyState, Notice, Pagination, Segmented, Skeleton, button, field, surface, text } from "../design";
import { formatTime } from "../settings/AuditPage";
import { useAgents, useAgentVersions } from "./agents";
import {
  conversationFilters,
  type ConversationFilters,
  type ConversationMessage,
  type ConversationDetail,
  type ConversationPage as ConversationPageData,
  type ConversationPath,
  type ConversationSummary,
  PAGE_SIZE,
  useConversation,
  useConversations,
  useConversationTrace,
  useDeleteConversation,
} from "./conversations";
import { useOrganisationRole } from "./ProjectsPage";
import { TraceContent, TraceFold } from "./Trace";

const PROJECT_ROUTE = "/signed-in/organisations/$organisationId/projects/$projectId";
const PROJECT_LIST = "/organisations/$organisationId/projects/$projectId/conversations/$conversationId";
const AGENT_LIST = "/organisations/$organisationId/projects/$projectId/agents/$agentId/conversations/$conversationId";
// Why a Playground Conversation is flagged.
const PLAYGROUND_WHY = "tried in the Playground by an Editor; left out of analytics";

/** The list's filters as the Agent's Conversations view keeps them: the Agent is the view's own. */
export type AgentConversationFilters = Omit<ConversationFilters, "agent">;

/** The Agent view's filters from its URL, leaving out an Agent (the view fixes it). */
export function agentConversationFilters(search: object): AgentConversationFilters {
  const filters = conversationFilters(search as Record<string, unknown>);
  delete filters.agent;
  return filters;
}

/** Where the list sits: the Project's Conversations section, or one Agent's Conversations view. */
interface ConversationsFrame {
  /** The level of the list's heading; the transcript's is one below. */
  level: 2 | 3;
  /** The Agent the list is fixed to, in an Agent's view. */
  agentId?: string;
}

const FrameContext = createContext<ConversationsFrame>({ level: 2 });

/** A Conversation's Message Feedback counts, such as "1 up · 2 down", or "None". */
function thumbsText({ thumbs_up: up, thumbs_down: down }: ConversationSummary): string {
  const counts = [up > 0 && `${String(up)} up`, down > 0 && `${String(down)} down`].filter(Boolean);
  return counts.length === 0 ? "None" : counts.join(" · ");
}

/** A Conversation's Conversation Rating, such as "4 of 5", or "Not rated". */
function ratingText(rating: number | null): string {
  return rating === null ? "Not rated" : `${String(rating)} of 5`;
}

/** The first question, or why there is none to show. */
function previewText(conversation: ConversationSummary): string {
  if (conversation.deleted_at !== null) return "(deleted on request)";
  if (conversation.preview !== null) return conversation.preview;
  return conversation.message_count === 0 ? "(nothing asked yet)" : "(text purged)";
}

/** How many of a Conversation's replies have a Guardrail outcome, such as "2 events", or "None". */
function guardrailText({ guardrail_events: events }: ConversationSummary): string {
  if (events === 0) return "None";
  return `${String(events)} ${events === 1 ? "event" : "events"}`;
}

const versionsText = (conversation: ConversationSummary) =>
  conversation.version_numbers.length === 0 ? "Draft" : conversation.version_numbers.map((n) => `v${String(n)}`).join(", ");

function Kind({ conversation }: { conversation: ConversationSummary }) {
  if (!conversation.is_playground) return <>Visitor</>;
  return (
    <span
      title={`T${PLAYGROUND_WHY.slice(1)}.`}
      className="inline-flex items-center rounded-full bg-flag-soft px-2 py-px text-xs font-medium text-flag"
    >
      Playground
    </span>
  );
}

/** The Versions of the chosen Agent, newest first; disabled until an Agent is chosen. */
function VersionFilter({
  organisationId,
  projectId,
  agentId,
  value,
  onChange,
}: {
  organisationId: string;
  projectId: string;
  agentId: string | undefined;
  value: string;
  onChange: (value: string) => void;
}) {
  const versions = useAgentVersions(organisationId, projectId, agentId ?? "", agentId !== undefined);
  return (
    <label className={field.filter}>
      Version
      <select
        className={field.pill}
        value={value}
        disabled={agentId === undefined}
        onChange={(event) => {
          onChange(event.currentTarget.value);
        }}
      >
        <option value="">Every Version</option>
        {agentId !== undefined &&
          versions.data?.versions.map((version) => (
            <option key={version.id} value={version.id}>
              {`v${String(version.number)}`}
            </option>
          ))}
      </select>
    </label>
  );
}

/** The Agent filter: the Project's Agents, archived ones last. */
function AgentFilter({
  organisationId,
  projectId,
  value,
  onChange,
}: {
  organisationId: string;
  projectId: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const active = useAgents(organisationId, projectId);
  const archived = useAgents(organisationId, projectId, true);
  return (
    <label className={field.filter}>
      Agent
      <select
        className={field.pill}
        value={value}
        onChange={(event) => {
          onChange(event.currentTarget.value);
        }}
      >
        <option value="">Every Agent</option>
        {active.data?.map((agent) => (
          <option key={agent.id} value={agent.id}>
            {agent.name}
          </option>
        ))}
        {archived.data?.map((agent) => (
          <option key={agent.id} value={agent.id}>
            {agent.name} (archived)
          </option>
        ))}
      </select>
    </label>
  );
}

/** A pill select of fixed options. */
function Choice({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: [string, string][];
  onChange: (value: string) => void;
}) {
  return (
    <label className={field.filter}>
      {label}
      <select
        className={field.pill}
        value={value}
        onChange={(event) => {
          onChange(event.currentTarget.value);
        }}
      >
        {options.map(([option, name]) => (
          <option key={option} value={option}>
            {name}
          </option>
        ))}
      </select>
    </label>
  );
}

const SHOW = [
  { value: "visitors", label: "Visitors" },
  { value: "playground", label: "Playground" },
  { value: "both", label: "Both" },
] as const;

function Filters({
  organisationId,
  projectId,
  filters,
  agentId,
  onChange,
}: {
  organisationId: string;
  projectId: string;
  filters: ConversationFilters;
  /** The Agent the view is fixed to: no Agent filter, and its Versions offered. */
  agentId: string | undefined;
  onChange: (filters: ConversationFilters) => void;
}) {
  // Any change starts again from the first page; an emptied filter is left out.
  const set = (changes: Record<string, unknown>) => {
    onChange(conversationFilters({ ...filters, ...changes, page: undefined }));
  };
  const day = (key: "from" | "to") => (event: { currentTarget: { value: string } }) => {
    set({ [key]: event.currentTarget.value });
  };
  return (
    <fieldset className="flex flex-wrap items-end gap-x-3 gap-y-3">
      <legend className="sr-only">Filter Conversations</legend>
      {agentId === undefined && (
        <AgentFilter
          organisationId={organisationId}
          projectId={projectId}
          value={filters.agent ?? ""}
          onChange={(agent) => {
            // Versions belong to one Agent, so a new Agent clears the Version.
            set({ agent, version: undefined });
          }}
        />
      )}
      <VersionFilter
        organisationId={organisationId}
        projectId={projectId}
        agentId={agentId ?? filters.agent}
        value={filters.version ?? ""}
        onChange={(version) => {
          set({ version });
        }}
      />
      <label className={field.filter}>
        From (UTC)
        <input type="date" className={field.pill} value={filters.from ?? ""} onChange={day("from")} />
      </label>
      <label className={field.filter}>
        To (UTC)
        <input type="date" className={field.pill} value={filters.to ?? ""} onChange={day("to")} />
      </label>
      <div className={field.filter}>
        <span aria-hidden="true">Show</span>
        <div className="mt-1">
          <Segmented
            label="Show"
            options={SHOW}
            value={filters.show ?? "both"}
            onChange={(show) => {
              set({ show });
            }}
          />
        </div>
      </div>
      <Choice
        label="Feedback"
        value={filters.feedback ?? ""}
        options={[
          ["", "Any or none"],
          ["up", "Thumbs up"],
          ["down", "Thumbs down"],
          ["any", "With feedback"],
          ["none", "Without feedback"],
        ]}
        onChange={(feedback) => {
          set({ feedback });
        }}
      />
      <Choice
        label="Rating"
        value={String(filters.rating ?? "")}
        options={[
          ["", "Rated or not"],
          ...["5", "4", "3", "2", "1"].map((score): [string, string] => [score, `${score} of 5`]),
          ["any", "Rated"],
          ["none", "Not rated"],
        ]}
        onChange={(rating) => {
          set({ rating });
        }}
      />
      <Choice
        label="Guardrail"
        value={filters.guardrail ?? ""}
        options={[
          ["", "Any or none"],
          ["blocked", "Blocked"],
          ["flagged", "Flagged"],
          ["logged", "Logged"],
          ["replaced", "Replaced (Canary token)"],
          ["allowed", "Allowed unchecked"],
          ["any", "With a Guardrail event"],
          ["none", "Without"],
        ]}
        onChange={(guardrail) => {
          set({ guardrail });
        }}
      />
    </fieldset>
  );
}

/** One fact about a listed Conversation; `label` shows its name, otherwise it is for screen readers. */
function Fact({ name, label = false, mono = false, children }: { name: string; label?: boolean; mono?: boolean; children: ReactNode }) {
  return (
    <div className="flex items-center gap-1">
      <dt className={label ? "text-muted" : "sr-only"}>{name}</dt>
      <dd className={mono ? "font-mono text-ink-2" : "text-ink-2"}>{children}</dd>
    </div>
  );
}

/** The link to a listed Conversation, in the Project's section or the Agent's view, keeping the filters. */
function ConversationLink({ conversation, filters }: { conversation: ConversationSummary; filters: ConversationFilters }) {
  const { organisationId, projectId } = useParams({ from: PROJECT_ROUTE });
  const { agentId } = useContext(FrameContext);
  const className =
    "block min-w-0 truncate font-medium text-ink after:absolute after:inset-0 after:rounded-xl hover:text-accent aria-[current=page]:text-accent-ink";
  const conversationId = conversation.id;
  if (agentId !== undefined) {
    return (
      <Link
        to={AGENT_LIST}
        params={{ organisationId, projectId, agentId, conversationId }}
        search={agentConversationFilters(filters)}
        className={className}
      >
        {previewText(conversation)}
      </Link>
    );
  }
  return (
    <Link to={PROJECT_LIST} params={{ organisationId, projectId, conversationId }} search={filters} className={className}>
      {previewText(conversation)}
    </Link>
  );
}

function Results({ data, filters }: { data: ConversationPageData; filters: ConversationFilters }) {
  const { agentId, level } = useContext(FrameContext);
  if (data.items.length === 0) {
    const filtered = Object.keys(filters).some((key) => key !== "page");
    let description = "Visitors' Conversations with this Project's Agents, and the Playground's, will appear here.";
    if (agentId !== undefined) description = "Visitors' Conversations with this Agent, and the Playground's, will appear here.";
    return filtered ? (
      <p className={`${surface.panel} ${text.muted}`}>No Conversations match these filters.</p>
    ) : (
      <EmptyState icon="conversations" title="No Conversations yet" description={description} level={level === 2 ? 3 : 4} />
    );
  }
  return (
    <ul aria-label="Conversations" className={`${surface.card} flex flex-col gap-1 p-1.5`}>
      {data.items.map((conversation) => (
        <li
          key={conversation.id}
          className="relative rounded-xl px-3.5 py-3 hover:bg-sunken has-[[aria-current=page]]:bg-accent-soft"
        >
          <ConversationLink conversation={conversation} filters={filters} />
          <dl className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs">
            <Fact name="Started" mono>
              {formatTime(conversation.created_at)}
            </Fact>
            <Fact name="Agent">{conversation.agent_name}</Fact>
            <Fact name="With">
              <Kind conversation={conversation} />
            </Fact>
            <Fact name="Answered by" mono>
              {versionsText(conversation)}
            </Fact>
            <Fact name="Messages" label mono>
              {conversation.message_count}
            </Fact>
            <Fact name="Feedback" label>
              {thumbsText(conversation)}
            </Fact>
            <Fact name="Rating" label>
              {ratingText(conversation.rating)}
            </Fact>
            <Fact name="Guardrail" label>
              {guardrailText(conversation)}
            </Fact>
          </dl>
        </li>
      ))}
    </ul>
  );
}

function Pager({ data, onPage }: { data: ConversationPageData; onPage: (page: number) => void }) {
  const pages = Math.ceil(data.total / PAGE_SIZE);
  return (
    <div className="flex flex-col items-center gap-2">
      <Pagination label="Conversations pages" page={data.page} pageCount={pages} onPageChange={onPage} />
      <p className={text.small}>
        Page {data.page} of {pages} · {data.total} {data.total === 1 ? "Conversation" : "Conversations"}
      </p>
    </div>
  );
}

/**
 * The Conversations list with its filters, beside the open Conversation's transcript (the child
 * route's `Outlet`). In an Agent's view the list is fixed to that Agent.
 */
function ConversationsSplit({ search, agentId }: { search: object; agentId?: string }) {
  const { organisationId } = useOrganisationRole();
  const { projectId } = useParams({ from: PROJECT_ROUTE });
  const headingId = useId();
  // The router passes unknown search values through from its parent routes, so filter again.
  const filters = conversationFilters(search as Record<string, unknown>);
  const navigate = useNavigate();
  const conversations = useConversations(organisationId, projectId, agentId === undefined ? filters : { ...filters, agent: agentId });
  const frame: ConversationsFrame = agentId === undefined ? { level: 2 } : { level: 3, agentId };
  const show = (next: ConversationFilters) => {
    void navigate({ to: ".", search: agentId === undefined ? next : agentConversationFilters(next) });
  };
  const Heading = frame.level === 2 ? "h2" : "h3";

  let body;
  if (conversations.isError) {
    body = <Notice tone="error">The Conversations could not be loaded. Try again shortly.</Notice>;
  } else if (conversations.data === undefined) {
    body = <Skeleton label="Loading the Conversations" />;
  } else {
    body = (
      <>
        <Results data={conversations.data} filters={filters} />
        {conversations.data.total > 0 && (
          <Pager
            data={conversations.data}
            onPage={(page) => {
              show({ ...filters, page });
            }}
          />
        )}
      </>
    );
  }

  return (
    <FrameContext.Provider value={frame}>
      <section aria-labelledby={headingId} className="flex flex-col gap-5">
        <Heading id={headingId} className={frame.level === 2 ? "text-2xl font-medium tracking-[-0.01em] text-ink" : text.heading}>
          Conversations
        </Heading>
        <Filters organisationId={organisationId} projectId={projectId} filters={filters} agentId={agentId} onChange={show} />
        <div className="flex flex-wrap items-start gap-6">
          <div className="flex min-w-0 flex-[1_1_300px] flex-col gap-3 lg:max-w-[380px]">{body}</div>
          <div className="min-w-0 flex-[999_1_480px]">
            <Outlet />
          </div>
        </div>
      </section>
    </FrameContext.Provider>
  );
}

/** The Project's Conversations section: Visitors' and the Playground's, filtered and in pages. */
export function ConversationsTab() {
  const search = useSearch({ from: "/signed-in/organisations/$organisationId/projects/$projectId/conversations" });
  return <ConversationsSplit search={search} />;
}

/** The Agent's Conversations view: the same list, fixed to the Agent. */
export function AgentConversationsView() {
  const { agentId } = useParams({ from: "/signed-in/organisations/$organisationId/projects/$projectId/agents/$agentId" });
  const search = useSearch({ from: "/signed-in/organisations/$organisationId/projects/$projectId/agents/$agentId/conversations" });
  return <ConversationsSplit search={search} agentId={agentId} />;
}

/** Beside the list until a Conversation is opened. */
export function NoConversationChosen() {
  const { level } = useContext(FrameContext);
  return (
    <EmptyState
      icon="conversations"
      title="Choose a Conversation"
      description="Open one from the list to read its Messages, each answer's Trace, and the Visitor's feedback."
      level={level === 2 ? 3 : 4}
    />
  );
}

/** The Visitor's Message Feedback on a reply: the thumb, the Version it counts for, when, and any comment. */
function FeedbackNote({ message, visitor }: { message: ConversationMessage; visitor: boolean }) {
  const feedback = message.feedback;
  if (feedback === null) {
    return visitor ? <p className={text.small}>No feedback</p> : null;
  }
  const version = versionText(feedback.agent_version_number);
  return (
    <div role="group" aria-label="Visitor feedback" className="rounded-xl bg-sunken px-3.5 py-2.5 text-sm text-ink-2">
      <p>
        <span className={feedback.rating === "up" ? "font-medium text-accent-ink" : "font-medium text-danger"}>
          {feedback.rating === "up" ? "Thumbs up" : "Thumbs down"}
        </span>
        {` · for ${version} · ${formatTime(feedback.updated_at)}`}
      </p>
      {feedback.comment !== null && (
        <blockquote className="mt-1 whitespace-pre-wrap border-l-2 border-field pl-2 text-ink">{feedback.comment}</blockquote>
      )}
    </div>
  );
}

const versionText = (number: number | null) => (number === null ? "the Draft" : `Agent Version v${String(number)}`);

/**
 * The Visitor's Conversation Rating: the score, the Version it counts for (the last reply's
 * before it), when, whether they dismissed the prompt, and the change log.
 */
function RatingNote({ rating }: { rating: ConversationDetail["rating"] }) {
  const { level } = useContext(FrameContext);
  const Heading = level === 2 ? "h4" : "h5";
  return (
    <section aria-label="Conversation Rating" className="rounded-xl border border-line px-4 py-3 text-sm text-ink-2">
      <Heading className="font-medium text-ink">Conversation Rating</Heading>
      {rating?.score == null ? (
        <p>Not rated</p>
      ) : (
        <p>
          <span className="font-medium text-ink">{`Rated ${String(rating.score)} of 5`}</span>
          {` · for ${versionText(rating.agent_version_number)} · ${formatTime(rating.rated_at as string)}`}
        </p>
      )}
      {rating?.prompt_dismissed_at != null && (
        <p className="text-muted">{`The Visitor dismissed the rating prompt · ${formatTime(rating.prompt_dismissed_at)}`}</p>
      )}
      {rating !== null && rating.changes.length > 0 && (
        <>
          <p className="mt-2 font-medium text-ink">Changes</p>
          <ol aria-label="Rating changes" className="list-inside list-decimal">
            {rating.changes.map((change) => (
              <li key={change.changed_at + String(change.score)}>
                {change.previous_score === null
                  ? `Rated ${String(change.score)}`
                  : `Changed from ${String(change.previous_score)} to ${String(change.score)}`}
                {` · for ${versionText(change.agent_version_number)} · ${formatTime(change.changed_at)}`}
              </li>
            ))}
          </ol>
        </>
      )}
    </section>
  );
}

/** A Message's text, or a note that it was purged and why. */
function MessageText({ message, deletedAt }: { message: ConversationMessage; deletedAt: string | null }) {
  if (message.purged_at === null) return <p className="whitespace-pre-wrap text-[15px] text-ink">{message.content}</p>;
  // The daily purge may have cleared it before the Conversation was deleted.
  const why =
    message.purged_at === deletedAt ? "the Conversation was deleted on request" : "it was older than the Retention Window";
  return <p className="text-sm italic text-muted">{`Text purged ${formatTime(message.purged_at)}: ${why}.`}</p>;
}

/**
 * Whether the input Guardrail blocked the question this reply answers: the reply is the refusal
 * text, so it names no model, and it isn't the fallback (which names none either).
 */
function blocked(message: ConversationMessage): boolean {
  return message.model_name === null && !message.fallback;
}

/** A reply's usage on its Trace's summary row, as the Playground shows it. */
function usage(message: ConversationMessage): string {
  return `${String(message.input_tokens)} input and ${String(message.output_tokens)} output tokens · ${String(message.latency_ms)} ms`;
}

function MessageItem({
  message,
  asker,
  agentName,
  deletedAt,
  path,
}: {
  message: ConversationMessage;
  asker: string;
  agentName: string;
  deletedAt: string | null;
  path: ConversationPath;
}) {
  if (message.role === "user") {
    return (
      <li aria-label={asker} className="flex flex-col items-end gap-1">
        <p className={text.small}>{asker}</p>
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-sunken px-4 py-2.5">
          <MessageText message={message} deletedAt={deletedAt} />
        </div>
      </li>
    );
  }
  return (
    <li aria-label={agentName} className="flex gap-3">
      <span
        aria-hidden="true"
        className="flex size-8 shrink-0 items-center justify-center rounded-full bg-accent-soft text-sm font-semibold text-accent-ink"
      >
        {agentName.charAt(0).toUpperCase()}
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <p className="flex flex-wrap items-center gap-2 text-xs text-muted">
          <span className="font-medium text-ink-2">{agentName}</span>
          {message.agent_version_number === null ? (
            <Badge kind="draft" title="Answered by the Draft, in the Playground." />
          ) : (
            <Badge kind="version" version={message.agent_version_number} />
          )}
          {message.fallback && <span>Fallback reply</span>}
          {blocked(message) && <Badge kind="blocked" title="The input Guardrail blocked the question: the model wasn't asked." />}
        </p>
        <MessageText message={message} deletedAt={deletedAt} />
        <FeedbackNote message={message} visitor={asker === "Visitor"} />
        <TraceFold summary={usage(message)}>
          <ConversationTrace path={{ ...path, message_id: message.id }} />
        </TraceFold>
      </div>
    </li>
  );
}

function ConversationTrace({ path }: { path: ConversationPath & { message_id: string } }) {
  return <TraceContent trace={useConversationTrace(path)} />;
}

/**
 * An Owner deletes the Conversation on request, after confirming: its text and feedback comments are
 * purged at once; its numbers stay in the metrics.
 */
function DeleteConversation({ path }: { path: ConversationPath }) {
  const remove = useDeleteConversation(path);
  const [confirming, setConfirming] = useState(false);
  return (
    <>
      <button
        type="button"
        className={button.danger}
        onClick={() => {
          setConfirming(true);
        }}
      >
        Delete Conversation
      </button>
      <ConfirmDialog
        open={confirming}
        title="Delete Conversation"
        destructive
        busy={remove.isPending}
        confirmLabel="Yes, delete it"
        onCancel={() => {
          setConfirming(false);
        }}
        onConfirm={() => {
          remove.mutate(undefined, {
            onSettled: () => {
              setConfirming(false);
            },
          });
        }}
      >
        Its Messages&apos; text and feedback comments will be purged now and can&apos;t be recovered. Its numbers stay in the
        metrics. The deletion is recorded in the Audit log.
      </ConfirmDialog>
      {remove.isError && <Notice tone="error">The Conversation could not be deleted. Try again shortly.</Notice>}
    </>
  );
}

/** One Conversation beside the list: its Messages, each answer with the Version that answered and its Trace. */
export function ConversationPage() {
  const { organisationId, isOwner } = useOrganisationRole();
  const { level } = useContext(FrameContext);
  // The open Conversation, in the Project's section or in an Agent's view.
  const params = useParams({ strict: false });
  const projectId = params.projectId as string;
  const conversationId = params.conversationId as string;
  const path = { organisation_id: organisationId, project_id: projectId, conversation_id: conversationId };
  const conversation = useConversation(path);
  const Heading = level === 2 ? "h3" : "h4";

  let body;
  if (conversation.isError) {
    body = <Notice tone="error">The Conversation could not be found.</Notice>;
  } else if (conversation.data === undefined) {
    body = <Skeleton label="Loading the Conversation" />;
  } else {
    const data = conversation.data;
    const kind = data.is_playground ? `Playground Conversation · ${PLAYGROUND_WHY}` : "Visitor Conversation";
    body = (
      <>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 flex-col gap-1">
            <Heading className={text.heading}>Conversation with {data.agent_name}</Heading>
            <p className={text.muted}>
              {kind} · started {formatTime(data.created_at)} · last active {formatTime(data.last_activity_at)}
            </p>
          </div>
          {data.deleted_at === null && isOwner && <DeleteConversation path={path} />}
        </div>
        {data.deleted_at !== null && (
          <p className="text-sm font-medium text-ink-2">{`Deleted on request ${formatTime(data.deleted_at)}. Its numbers stay in the metrics.`}</p>
        )}
        <ol aria-label="Messages" className="flex flex-col gap-5">
          {data.messages.map((message) => (
            <MessageItem
              key={message.id}
              message={message}
              asker={data.is_playground ? "Editor" : "Visitor"}
              agentName={data.agent_name}
              deletedAt={data.deleted_at}
              path={path}
            />
          ))}
        </ol>
        {!data.is_playground && <RatingNote rating={data.rating} />}
      </>
    );
  }

  return (
    <article aria-label="Conversation" className={`${surface.panel} flex flex-col gap-5`}>
      {body}
    </article>
  );
}
