import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { type SubmitEvent, useCallback, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import {
  type Agent,
  type Citation,
  agentFailure,
  askPlayground,
  instructionsUsed,
  startConversation,
  useAgent,
  useArchiveOrRestoreAgent,
  useDeleteAgent,
} from "./agents";
import { AgentEmbed } from "./AgentEmbed";
import { LiveHistory } from "./AgentLiveHistory";
import { LiveStatus, PublishAgent } from "./AgentPublish";
import { DraftEditor } from "./DraftEditor";
import { useInstructionsVersions } from "./instructions";
import { BUTTON, INPUT, useOrganisationRole } from "./ProjectsPage";
import { TraceDrawer } from "./TraceDrawer";

function useAgentParams() {
  return useParams({
    from: "/signed-in/organisations/$organisationId/projects/$projectId/agents/$agentId",
  });
}

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  usage?: string;
  // Which Project Instructions the answer ran with, once it is saved.
  instructions?: string;
  citations?: Citation[];
  // Set once the answer is saved, so its Trace can be opened.
  messageId?: string;
};

/** Where a citation chip leads: the cited Chunk in the Document viewer. */
function chunkHref(
  organisationId: string,
  projectId: string,
  citation: Citation,
): string {
  return `/organisations/${organisationId}/projects/${projectId}/documents/${citation.document_id}#chunk-${citation.chunk_id}`;
}

function Sources({
  citations,
  organisationId,
  projectId,
}: {
  citations: Citation[];
  organisationId: string;
  projectId: string;
}) {
  return (
    <ul aria-label="Sources" className="mt-2 flex flex-wrap gap-2">
      {citations.map((citation) => (
        <li key={citation.chunk_id}>
          <a
            href={chunkHref(organisationId, projectId, citation)}
            className="inline-flex gap-1 rounded-full border border-slate-300 px-2 py-0.5 text-xs text-slate-900 underline-offset-2 hover:underline"
          >
            <span className="font-semibold">{citation.label}</span>{" "}
            <span>{citation.document_name}</span>
          </a>
        </li>
      ))}
    </ul>
  );
}

/** Chooses the Project Instructions the Playground answers with: the Instructions Draft (the
 * default) or any Instructions Version, so either can be tried before it is published. */
function InstructionsPicker({
  organisationId,
  projectId,
  value,
  onChange,
}: {
  organisationId: string;
  projectId: string;
  value: string;
  onChange: (versionId: string) => void;
}) {
  const history = useInstructionsVersions(organisationId, projectId);
  let hint =
    "Answers follow the Instructions Draft unless you choose a Version.";
  if (history.isError)
    hint =
      "The Instructions Versions could not be loaded, so answers follow the Instructions Draft.";
  else if (history.data?.versions.length === 0)
    hint =
      "No Instructions Versions are published yet, so answers follow the Instructions Draft.";
  return (
    <div className="space-y-1">
      <label
        htmlFor="playground-instructions"
        className="block text-sm font-medium"
      >
        Instructions
      </label>
      <select
        id="playground-instructions"
        aria-describedby="playground-instructions-hint"
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
        className={INPUT}
      >
        <option value="">Instructions Draft</option>
        {history.data?.versions.map((version) => (
          <option key={version.id} value={version.id}>
            {`v${String(version.number)}${version.id === history.data.current_version_id ? " (Current)" : ""} · ${version.note}`}
          </option>
        ))}
      </select>
      <p id="playground-instructions-hint" className="text-xs text-slate-700">
        {hint}
      </p>
    </div>
  );
}

/** Chat with the Agent's Draft. The answer streams in token by token. */
function Playground({
  agent,
  organisationId,
}: {
  agent: Agent;
  organisationId: string;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [question, setQuestion] = useState("");
  // The Instructions Version questions are asked with; "" for the Instructions Draft.
  const [instructionsVersionId, setInstructionsVersionId] = useState("");
  const [tracing, setTracing] = useState<string | null>(null);
  // Set when a reset has started a new Conversation, until the next question.
  const [wasReset, setWasReset] = useState(false);
  const closeTrace = useCallback(() => {
    setTracing(null);
  }, []);
  const path = {
    organisation_id: organisationId,
    project_id: agent.project_id,
    agent_id: agent.id,
  };

  function appendToAnswer(update: (answer: ChatMessage) => ChatMessage) {
    setMessages((current) => [
      ...current.slice(0, -1),
      update(current[current.length - 1] as ChatMessage),
    ]);
  }

  async function ask(question: string) {
    setError(null);
    setWasReset(false);
    setPending(true);
    setMessages((current) => [
      ...current,
      { role: "user", content: question },
      { role: "assistant", content: "" },
    ]);
    try {
      const conversation = conversationId ?? (await startConversation(path)).id;
      setConversationId(conversation);
      const done = await askPlayground(
        { ...path, conversation_id: conversation },
        question,
        instructionsVersionId || null,
        (text) => {
          appendToAnswer((answer) => ({
            ...answer,
            content: answer.content + text,
          }));
        },
        (citation) => {
          appendToAnswer((answer) => ({
            ...answer,
            citations: [...(answer.citations ?? []), citation],
          }));
        },
        (text) => {
          // The answer leaked the Canary token: what streamed is replaced by the fallback text.
          appendToAnswer((answer) => ({ ...answer, content: text }));
        },
      );
      appendToAnswer((answer) => ({
        ...answer,
        messageId: done.message_id,
        instructions: `Instructions: ${instructionsUsed(done)}`,
        usage: `${String(done.input_tokens)} input and ${String(done.output_tokens)} output tokens · ${String(done.latency_ms)} ms`,
      }));
    } catch (failure) {
      // Drop the answer, and whatever of it streamed before the failure.
      setMessages((current) => current.slice(0, -1));
      setError(failure as Error);
    } finally {
      setPending(false);
    }
  }

  /** Starts a new Playground Conversation; the next question is asked in it. */
  async function reset() {
    setError(null);
    setWasReset(false);
    setPending(true);
    try {
      const conversation = await startConversation(path);
      setConversationId(conversation.id);
      setMessages([]);
      setTracing(null);
      setWasReset(true);
    } catch (failure) {
      setError(failure as Error);
    } finally {
      setPending(false);
    }
  }

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const asked = question.trim();
    if (!asked) return;
    setQuestion("");
    void ask(asked);
  }

  return (
    <section aria-labelledby="playground-heading" className="space-y-3">
      <h2 id="playground-heading" className="text-lg font-semibold">
        Playground
      </h2>
      <p className="text-sm text-slate-700">
        Chat with this Draft. Playground Conversations are recorded but kept out
        of metrics.
      </p>
      <InstructionsPicker
        organisationId={organisationId}
        projectId={agent.project_id}
        value={instructionsVersionId}
        onChange={setInstructionsVersionId}
      />
      <div className="flex items-center gap-3">
        <button
          type="button"
          disabled={pending}
          onClick={() => {
            void reset();
          }}
          className="text-sm text-slate-900 underline disabled:opacity-50"
        >
          Reset conversation
        </button>
        <p role="status" className="text-sm text-slate-700">
          {wasReset ? "Started a new conversation." : ""}
        </p>
      </div>
      <ol
        aria-label="Playground messages"
        aria-live="polite"
        className="space-y-2"
      >
        {messages.map((message, index) => (
          <li
            key={index}
            aria-label={message.role === "user" ? "You" : agent.name}
            className={`rounded px-3 py-2 text-sm ${message.role === "user" ? "bg-slate-100" : "border border-slate-200 bg-white"}`}
          >
            <p className="whitespace-pre-wrap">{message.content}</p>
            {message.citations && (
              <Sources
                citations={message.citations}
                organisationId={organisationId}
                projectId={agent.project_id}
              />
            )}
            {message.usage && (
              <p className="mt-1 text-xs text-slate-700">{message.usage}</p>
            )}
            {message.instructions && (
              <p className="text-xs text-slate-700">{message.instructions}</p>
            )}
            {message.messageId && (
              <button
                type="button"
                value={message.messageId}
                onClick={(event) => {
                  setTracing(event.currentTarget.value);
                }}
                className="mt-1 text-xs text-slate-700 underline"
              >
                Trace
              </button>
            )}
          </li>
        ))}
      </ol>
      <FormError message={agentFailure(error)} />
      <form
        aria-label="Ask the Draft"
        onSubmit={onSubmit}
        className="space-y-2"
      >
        <label htmlFor="question" className="block text-sm font-medium">
          Question
        </label>
        <textarea
          id="question"
          name="question"
          rows={2}
          maxLength={4000}
          value={question}
          onChange={(event) => {
            setQuestion(event.target.value);
          }}
          className={INPUT}
        />
        <button type="submit" disabled={pending} className={BUTTON}>
          {pending ? "Answering…" : "Send"}
        </button>
      </form>
      {tracing && conversationId && (
        <TraceDrawer
          path={{
            ...path,
            conversation_id: conversationId,
            message_id: tracing,
          }}
          onClose={closeTrace}
        />
      )}
    </section>
  );
}

function ArchiveAgent({
  agent,
  organisationId,
}: {
  agent: Agent;
  organisationId: string;
}) {
  const archive = useArchiveOrRestoreAgent(
    organisationId,
    agent.project_id,
    "archive",
  );
  const [confirming, setConfirming] = useState(false);
  return (
    <div className="space-y-2">
      <FormError message={agentFailure(archive.error)} />
      {confirming ? (
        <div className="space-y-2">
          <p className="text-sm text-slate-700">
            {agent.name} will be hidden from the Agents list and the Playground
            will be off. Its Draft and Conversations are kept. An Owner can
            restore it.
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              className={BUTTON}
              disabled={archive.isPending}
              onClick={() => {
                archive.mutate(agent.id, {
                  onSettled: () => {
                    setConfirming(false);
                  },
                });
              }}
            >
              Yes, archive {agent.name}
            </button>
            <button
              type="button"
              className={BUTTON}
              onClick={() => {
                setConfirming(false);
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          className={BUTTON}
          onClick={() => {
            archive.reset();
            setConfirming(true);
          }}
        >
          Archive Agent
        </button>
      )}
    </div>
  );
}

/** Owners only, on an archived Agent: deletion is confirmed by typing the Agent's name exactly. */
function DeleteAgentPermanently({
  agent,
  organisationId,
}: {
  agent: Agent;
  organisationId: string;
}) {
  const remove = useDeleteAgent(organisationId, agent.project_id, agent.id);
  const navigate = useNavigate();
  const [confirming, setConfirming] = useState(false);
  const [typed, setTyped] = useState("");
  const title = `Delete ${agent.name} permanently`;

  if (!confirming) {
    return (
      <button
        type="button"
        className={BUTTON}
        onClick={() => {
          remove.reset();
          setTyped("");
          setConfirming(true);
        }}
      >
        Delete permanently
      </button>
    );
  }

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    remove.mutate(typed, {
      onSuccess: () => {
        void navigate({
          to: "/organisations/$organisationId/projects/$projectId/agents",
          params: { organisationId, projectId: agent.project_id },
          search: { deleted: agent.name },
        });
      },
    });
  }

  return (
    <form
      aria-label={title}
      onSubmit={onSubmit}
      className="space-y-2 rounded border border-red-300 bg-white p-3 text-slate-900"
    >
      <p>
        Deleting {agent.name} removes its Draft and Conversations for good.
        This can&apos;t be undone.
      </p>
      <FormError message={agentFailure(remove.error)} />
      <div>
        <label
          htmlFor="delete-agent-name"
          className="block text-sm font-medium"
        >
          Type {agent.name} to confirm
        </label>
        <input
          id="delete-agent-name"
          autoComplete="off"
          className={INPUT}
          value={typed}
          onChange={(event) => {
            setTyped(event.target.value);
          }}
        />
      </div>
      <div className="flex gap-2">
        <button
          type="submit"
          className="rounded border border-red-800 bg-red-700 px-3 py-1 text-sm text-white hover:bg-red-800 disabled:border-slate-400 disabled:bg-slate-200 disabled:text-slate-600"
          disabled={typed !== agent.name || remove.isPending}
        >
          {title}
        </button>
        <button
          type="button"
          className={BUTTON}
          onClick={() => {
            setConfirming(false);
          }}
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

function ArchivedAgentNotice({
  agent,
  organisationId,
  isOwner,
}: {
  agent: Agent;
  organisationId: string;
  isOwner: boolean;
}) {
  const restore = useArchiveOrRestoreAgent(
    organisationId,
    agent.project_id,
    "restore",
  );
  return (
    <div
      role="status"
      aria-label="Archived"
      className="space-y-2 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950"
    >
      <p>
        This Agent is archived. It is hidden from the Agents list and the
        Playground is off.{" "}
        {isOwner ? "Restore it to use it again." : "Only Owners can restore it."}
      </p>
      <FormError message={agentFailure(restore.error)} />
      {isOwner && (
        <button
          type="button"
          className={BUTTON}
          disabled={restore.isPending}
          onClick={() => {
            restore.mutate(agent.id);
          }}
        >
          Restore {agent.name}
        </button>
      )}
      {isOwner && (
        <DeleteAgentPermanently agent={agent} organisationId={organisationId} />
      )}
    </div>
  );
}

/** One Agent: its Draft beside the Playground, and Archive; an archived Agent's Draft is read
 * only, without the Playground, and Owners can restore or permanently delete it. */
export function AgentPage() {
  const { organisationId, isOwner } = useOrganisationRole();
  const { projectId, agentId } = useAgentParams();
  const agent = useAgent(organisationId, projectId, agentId);

  let body;
  if (agent.isPending) {
    body = <p role="status">Loading the Agent…</p>;
  } else if (agent.isError) {
    body = <p role="alert">The Agent could not be found.</p>;
  } else {
    const archived = agent.data.archived_at !== null;
    body = (
      <>
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-semibold">{agent.data.name}</h2>
              <LiveStatus agent={agent.data} />
            </div>
            {!agent.data.live_version && (
              <p className="text-sm text-slate-700">
                Visitors can&apos;t use it until you publish it.
              </p>
            )}
          </div>
          {!archived && (
            <ArchiveAgent agent={agent.data} organisationId={organisationId} />
          )}
        </div>
        {!archived && (
          <PublishAgent
            key={`publish-${agent.data.id}`}
            agent={agent.data}
            organisationId={organisationId}
          />
        )}
        {!archived && (
          <AgentEmbed
            key={`embed-${agent.data.id}`}
            agent={agent.data}
            organisationId={organisationId}
          />
        )}
        {archived && (
          <ArchivedAgentNotice
            agent={agent.data}
            organisationId={organisationId}
            isOwner={isOwner}
          />
        )}
        <LiveHistory
          key={`live-history-${agent.data.id}`}
          agent={agent.data}
          organisationId={organisationId}
          archived={archived}
        />
        <div className="grid gap-8 lg:grid-cols-2">
          <DraftEditor
            key={`${agent.data.id}-${String(archived)}`}
            agent={agent.data}
            organisationId={organisationId}
          />
          {!archived && (
            <Playground
              key={`playground-${agent.data.id}`}
              agent={agent.data}
              organisationId={organisationId}
            />
          )}
        </div>
      </>
    );
  }

  return (
    <section aria-label="Agent" className="space-y-4">
      <Link
        to="/organisations/$organisationId/projects/$projectId/agents"
        params={{ organisationId, projectId }}
        className="text-sm text-slate-700 underline"
      >
        All Agents
      </Link>
      {body}
    </section>
  );
}
