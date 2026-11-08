import { Link, useNavigate, useParams, useSearch } from "@tanstack/react-router";
import { useState } from "react";

import { formatTime } from "../settings/AuditPage";
import { useAgents, useAgentVersions } from "./agents";
import {
  conversationFilters,
  type ConversationFilters,
  type ConversationMessage,
  type ConversationDetail,
  type ConversationPage,
  type ConversationPath,
  type ConversationSummary,
  PAGE_SIZE,
  useConversation,
  useConversations,
  useConversationTrace,
} from "./conversations";
import { BUTTON, INPUT, useOrganisationRole } from "./ProjectsPage";
import { answeredBy, TraceDrawerFrame } from "./TraceDrawer";

const LIST_ROUTE = "/signed-in/organisations/$organisationId/projects/$projectId/conversations";
const DETAIL_ROUTE = "/signed-in/organisations/$organisationId/projects/$projectId/conversations/$conversationId";
// Why a Playground Conversation is flagged.
const PLAYGROUND_WHY = "tried in the Playground by an Editor; left out of analytics";

function useListParams() {
  return useParams({ from: LIST_ROUTE });
}

/** A Conversation's Message Feedback counts, such as "1 up · 2 down", or "None". */
function thumbsText({ thumbs_up: up, thumbs_down: down }: ConversationSummary): string {
  const counts = [up > 0 && `${String(up)} up`, down > 0 && `${String(down)} down`].filter(Boolean);
  return counts.length === 0 ? "None" : counts.join(" · ");
}

/** A Conversation's Conversation Rating, such as "4 of 5", or "Not rated". */
function ratingText(rating: number | null): string {
  return rating === null ? "Not rated" : `${String(rating)} of 5`;
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
    <span title={`T${PLAYGROUND_WHY.slice(1)}.`} className="rounded bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900">
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
    <label className="flex flex-col gap-1 text-sm">
      Version
      <select
        className={INPUT}
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

function Filters({
  organisationId,
  projectId,
  filters,
  onChange,
}: {
  organisationId: string;
  projectId: string;
  filters: ConversationFilters;
  onChange: (filters: ConversationFilters) => void;
}) {
  const active = useAgents(organisationId, projectId);
  const archived = useAgents(organisationId, projectId, true);
  // Any change starts again from the first page; an emptied filter is left out.
  const set = (changes: Record<string, unknown>) => {
    onChange(conversationFilters({ ...filters, ...changes, page: undefined }));
  };
  const value = (key: "from" | "to") => (event: { currentTarget: { value: string } }) => {
    set({ [key]: event.currentTarget.value });
  };
  return (
    <fieldset className="mt-4 flex flex-wrap items-end gap-4">
      <legend className="sr-only">Filter Conversations</legend>
      <label className="flex flex-col gap-1 text-sm">
        Agent
        <select
          className={INPUT}
          value={filters.agent ?? ""}
          onChange={(event) => {
            // Versions belong to one Agent, so a new Agent clears the Version.
            set({ agent: event.currentTarget.value, version: undefined });
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
      <VersionFilter
        organisationId={organisationId}
        projectId={projectId}
        agentId={filters.agent}
        value={filters.version ?? ""}
        onChange={(version) => {
          set({ version });
        }}
      />
      <label className="flex flex-col gap-1 text-sm">
        From (UTC)
        <input type="date" className={INPUT} value={filters.from ?? ""} onChange={value("from")} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        To (UTC)
        <input type="date" className={INPUT} value={filters.to ?? ""} onChange={value("to")} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Show
        <select
          className={INPUT}
          value={filters.show ?? ""}
          onChange={(event) => {
            set({ show: event.currentTarget.value });
          }}
        >
          <option value="">Visitors and Playground</option>
          <option value="visitors">Visitors only</option>
          <option value="playground">Playground only</option>
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Feedback
        <select
          className={INPUT}
          value={filters.feedback ?? ""}
          onChange={(event) => {
            set({ feedback: event.currentTarget.value });
          }}
        >
          <option value="">Any or none</option>
          <option value="up">Thumbs up</option>
          <option value="down">Thumbs down</option>
          <option value="any">With feedback</option>
          <option value="none">Without feedback</option>
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Rating
        <select
          className={INPUT}
          value={String(filters.rating ?? "")}
          onChange={(event) => {
            set({ rating: event.currentTarget.value });
          }}
        >
          <option value="">Rated or not</option>
          {["5", "4", "3", "2", "1"].map((score) => (
            <option key={score} value={score}>
              {`${score} of 5`}
            </option>
          ))}
          <option value="any">Rated</option>
          <option value="none">Not rated</option>
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Guardrail
        <select
          className={INPUT}
          value={filters.guardrail ?? ""}
          onChange={(event) => {
            set({ guardrail: event.currentTarget.value });
          }}
        >
          <option value="">Any or none</option>
          <option value="blocked">Blocked</option>
          <option value="flagged">Flagged</option>
          <option value="logged">Logged</option>
          <option value="replaced">Replaced (Canary token)</option>
          <option value="allowed">Allowed unchecked</option>
          <option value="any">With a Guardrail event</option>
          <option value="none">Without</option>
        </select>
      </label>
    </fieldset>
  );
}

function Results({ data, filters }: { data: ConversationPage; filters: ConversationFilters }) {
  const { organisationId, projectId } = useListParams();
  if (data.items.length === 0) {
    const filtered = Object.keys(filters).some((key) => key !== "page");
    return (
      <p className="mt-6 text-slate-700">
        {filtered
          ? "No Conversations match these filters."
          : "No Conversations yet. Visitors' Conversations with this Project's Agents, and the Playground's, will appear here."}
      </p>
    );
  }
  return (
    <div className="mt-6 overflow-x-auto">
      <table className="w-full text-left text-sm" aria-label="Conversations">
        <thead>
          <tr className="text-slate-700">
            <th scope="col" className="py-2 pr-4 font-medium">Started</th>
            <th scope="col" className="py-2 pr-4 font-medium">Agent</th>
            <th scope="col" className="py-2 pr-4 font-medium">With</th>
            <th scope="col" className="py-2 pr-4 font-medium">Answered by</th>
            <th scope="col" className="py-2 pr-4 font-medium">Messages</th>
            <th scope="col" className="py-2 pr-4 font-medium">Feedback</th>
            <th scope="col" className="py-2 pr-4 font-medium">Rating</th>
            <th scope="col" className="py-2 pr-4 font-medium">Guardrail</th>
            <th scope="col" className="py-2 font-medium">First question</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((conversation) => (
            <tr key={conversation.id} className="border-t border-slate-200 align-top">
              <td className="whitespace-nowrap py-2 pr-4">{formatTime(conversation.created_at)}</td>
              <td className="py-2 pr-4">{conversation.agent_name}</td>
              <td className="py-2 pr-4">
                <Kind conversation={conversation} />
              </td>
              <td className="py-2 pr-4">{versionsText(conversation)}</td>
              <td className="py-2 pr-4">{conversation.message_count}</td>
              <td className="whitespace-nowrap py-2 pr-4">{thumbsText(conversation)}</td>
              <td className="whitespace-nowrap py-2 pr-4">{ratingText(conversation.rating)}</td>
              <td className="whitespace-nowrap py-2 pr-4">{guardrailText(conversation)}</td>
              <td className="py-2">
                <Link
                  to="/organisations/$organisationId/projects/$projectId/conversations/$conversationId"
                  params={{ organisationId, projectId, conversationId: conversation.id }}
                  search={filters}
                  className="underline"
                >
                  {conversation.preview ?? "(nothing asked yet)"}
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Pager({ data, onPage }: { data: ConversationPage; onPage: (page: number) => void }) {
  const pages = Math.ceil(data.total / PAGE_SIZE);
  return (
    <div className="mt-4 flex items-center gap-4">
      <button type="button" className={BUTTON} disabled={data.page <= 1} onClick={() => { onPage(data.page - 1); }}>
        Previous page
      </button>
      <p className="text-sm text-slate-700">
        Page {data.page} of {pages} · {data.total} {data.total === 1 ? "Conversation" : "Conversations"}
      </p>
      <button type="button" className={BUTTON} disabled={data.page >= pages} onClick={() => { onPage(data.page + 1); }}>
        Next page
      </button>
    </div>
  );
}

/** The Project's Conversations, Visitors' and the Playground's, filtered and in pages. */
export function ConversationsTab() {
  const { organisationId } = useOrganisationRole();
  const { projectId } = useListParams();
  // The router passes unknown search values through from its parent routes, so filter again.
  const filters = conversationFilters(useSearch({ from: LIST_ROUTE }));
  const navigate = useNavigate({ from: "/organisations/$organisationId/projects/$projectId/conversations" });
  const conversations = useConversations(organisationId, projectId, filters);
  const show = (next: ConversationFilters) => {
    void navigate({ search: next });
  };

  let body;
  if (conversations.isError) {
    body = (
      <p role="alert" className="mt-6">
        The Conversations could not be loaded. Try again shortly.
      </p>
    );
  } else if (conversations.data === undefined) {
    body = <p role="status" className="mt-6">Loading the Conversations…</p>;
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
    <section aria-labelledby="tab-heading">
      <h2 id="tab-heading" className="text-lg font-semibold">
        Conversations
      </h2>
      <Filters organisationId={organisationId} projectId={projectId} filters={filters} onChange={show} />
      {body}
    </section>
  );
}

function ConversationTrace({ path, onClose }: { path: ConversationPath & { message_id: string }; onClose: () => void }) {
  return <TraceDrawerFrame trace={useConversationTrace(path)} onClose={onClose} />;
}

/** The Visitor's Message Feedback on a reply: the thumb, the Version it counts for, when, and any comment. */
function FeedbackNote({ message, visitor }: { message: ConversationMessage; visitor: boolean }) {
  const feedback = message.feedback;
  if (feedback === null) {
    return visitor ? <p className="mt-2 text-xs text-slate-700">No feedback</p> : null;
  }
  const version = versionText(feedback.agent_version_number);
  return (
    <div role="group" aria-label="Visitor feedback" className="mt-2 rounded bg-slate-50 p-2 text-sm">
      <p>
        <span className={feedback.rating === "up" ? "font-medium text-emerald-800" : "font-medium text-red-800"}>
          {feedback.rating === "up" ? "Thumbs up" : "Thumbs down"}
        </span>
        {` · for ${version} · ${formatTime(feedback.updated_at)}`}
      </p>
      {feedback.comment !== null && (
        <blockquote className="mt-1 whitespace-pre-wrap border-l-2 border-slate-300 pl-2 text-slate-800">{feedback.comment}</blockquote>
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
  return (
    <section aria-label="Conversation Rating" className="rounded border border-slate-200 p-3 text-sm">
      <h3 className="font-medium">Conversation Rating</h3>
      {rating?.score == null ? (
        <p>Not rated</p>
      ) : (
        <p>
          <span className="font-medium">{`Rated ${String(rating.score)} of 5`}</span>
          {` · for ${versionText(rating.agent_version_number)} · ${formatTime(rating.rated_at as string)}`}
        </p>
      )}
      {rating?.prompt_dismissed_at != null && (
        <p className="text-slate-700">{`The Visitor dismissed the rating prompt · ${formatTime(rating.prompt_dismissed_at)}`}</p>
      )}
      {rating !== null && rating.changes.length > 0 && (
        <>
          <h4 className="mt-2 font-medium">Changes</h4>
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

function MessageItem({
  message,
  asker,
  agentName,
  onTrace,
}: {
  message: ConversationMessage;
  asker: string;
  agentName: string;
  onTrace: () => void;
}) {
  if (message.role === "user") {
    return (
      <li aria-label={asker} className="rounded bg-slate-100 p-3">
        <p className="text-xs font-medium text-slate-700">{asker}</p>
        <p className="whitespace-pre-wrap">{message.content}</p>
      </li>
    );
  }
  return (
    <li aria-label={agentName} className="rounded border border-slate-200 p-3">
      <p className="text-xs font-medium text-slate-700">
        {agentName} · {answeredBy(message)}
        {message.fallback && " · fallback reply"}
      </p>
      <p className="whitespace-pre-wrap">{message.content}</p>
      <FeedbackNote message={message} visitor={asker === "Visitor"} />
      <button type="button" className={`${BUTTON} mt-2`} onClick={onTrace}>
        Trace
      </button>
    </li>
  );
}

/** One Conversation: its Messages, each reply with the Version that answered and its Trace. */
export function ConversationPage() {
  const { organisationId } = useOrganisationRole();
  const { projectId, conversationId } = useParams({ from: DETAIL_ROUTE });
  const filters = useSearch({ from: DETAIL_ROUTE });
  const path = { organisation_id: organisationId, project_id: projectId, conversation_id: conversationId };
  const conversation = useConversation(path);
  const [traced, setTraced] = useState<string | null>(null);

  let body;
  if (conversation.isError) {
    body = <p role="alert">The Conversation could not be found.</p>;
  } else if (conversation.data === undefined) {
    body = <p role="status">Loading the Conversation…</p>;
  } else {
    const data = conversation.data;
    const kind = data.is_playground
      ? `Playground Conversation · ${PLAYGROUND_WHY}`
      : "Visitor Conversation";
    body = (
      <>
        <h2 className="text-xl font-semibold">Conversation with {data.agent_name}</h2>
        <p className="text-sm text-slate-700">
          {kind} · started {formatTime(data.created_at)} · last active {formatTime(data.last_activity_at)}
        </p>
        <ol aria-label="Messages" className="space-y-3">
          {data.messages.map((message) => (
            <MessageItem
              key={message.id}
              message={message}
              asker={data.is_playground ? "Editor" : "Visitor"}
              agentName={data.agent_name}
              onTrace={() => {
                setTraced(message.id);
              }}
            />
          ))}
        </ol>
        {!data.is_playground && <RatingNote rating={data.rating} />}
        {traced !== null && (
          <ConversationTrace
            key={traced}
            path={{ ...path, message_id: traced }}
            onClose={() => {
              setTraced(null);
            }}
          />
        )}
      </>
    );
  }

  return (
    <section aria-label="Conversation" className="space-y-4">
      <Link
        to="/organisations/$organisationId/projects/$projectId/conversations"
        params={{ organisationId, projectId }}
        search={filters}
        className="text-sm text-slate-700 underline"
      >
        All Conversations
      </Link>
      {body}
    </section>
  );
}
