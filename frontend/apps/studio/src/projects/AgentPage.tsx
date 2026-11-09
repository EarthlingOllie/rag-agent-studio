import { Link, Outlet, useNavigate, useParams } from "@tanstack/react-router";
import { createContext, type SubmitEvent, useCallback, useContext, useId, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import {
  button,
  ConfirmDialog,
  Dialog,
  EmptyState,
  field,
  Icon,
  Menu,
  type MenuItem,
  Notice,
  Skeleton,
  surface,
  text,
} from "../design";
import { TopBarActions } from "../shell/TopBarActions";
import {
  type Agent,
  type Citation,
  agentFailure,
  askPlayground,
  draftChangeFailure,
  instructionsUsed,
  startConversation,
  useAgent,
  useArchiveOrRestoreAgent,
  useDeleteAgent,
  useReplaceDraft,
} from "./agents";
import { AgentBranding } from "./AgentBranding";
import { AgentEmbed } from "./AgentEmbed";
import { LiveHistory } from "./AgentLiveHistory";
import { LiveStatus, PublishAgent } from "./AgentPublish";
import { AgentVersions } from "./AgentVersions";
import { DraftEditor } from "./DraftEditor";
import { useInstructionsVersions } from "./instructions";
import { useOrganisationRole } from "./ProjectsPage";
import { PlaygroundTrace, TraceFold } from "./Trace";
import { AgentAnalyticsLink } from "./AnalyticsTab";

const AGENT_ROUTE = "/signed-in/organisations/$organisationId/projects/$projectId/agents/$agentId";

function useAgentParams() {
  return useParams({ from: AGENT_ROUTE });
}

/** What every view of an open Agent shares, from the Agent page around them. */
type AgentView = {
  agent: Agent;
  organisationId: string;
  isOwner: boolean;
  /** Moves on whenever the Draft is replaced, so the editor starts again from the new Draft. */
  generation: number;
  onReplaced: () => void;
  /** The Draft editor's save state, shown in the top bar while the editor is open. */
  onDraftStatus: (status: string | null) => void;
};

const AgentViewContext = createContext<AgentView | null>(null);

/** The open Agent, inside one of its views (the Agent page renders them only once it is loaded). */
function useAgentView(): AgentView {
  return useContext(AgentViewContext) as AgentView;
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
  // The input Guardrail blocked the question: the content is the Agent's refusal text.
  refused?: boolean;
};

/** Where a citation chip leads: the cited Chunk in the Document viewer. */
function chunkHref(organisationId: string, projectId: string, citation: Citation): string {
  return `/organisations/${organisationId}/projects/${projectId}/documents/${citation.document_id}#chunk-${citation.chunk_id}`;
}

function Sources({ citations, organisationId, projectId }: { citations: Citation[]; organisationId: string; projectId: string }) {
  return (
    <ul aria-label="Sources" className="flex flex-wrap gap-2">
      {citations.map((citation) => (
        <li key={citation.chunk_id}>
          <a
            href={chunkHref(organisationId, projectId, citation)}
            className="inline-flex gap-1 rounded-full border border-line bg-surface px-2.5 py-0.5 text-xs text-ink-2 hover:border-accent hover:text-ink"
          >
            <span className="font-semibold text-accent">{citation.label}</span> <span>{citation.document_name}</span>
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
  let hint = "Answers follow the Instructions Draft unless you choose a Version.";
  if (history.isError) hint = "The Instructions Versions could not be loaded, so answers follow the Instructions Draft.";
  else if (history.data?.versions.length === 0) hint = "No Instructions Versions are published yet, so answers follow the Instructions Draft.";
  return (
    <div className="min-w-0 flex-1 basis-60">
      <label htmlFor="playground-instructions" className={field.label}>
        Instructions
      </label>
      <select
        id="playground-instructions"
        aria-describedby="playground-instructions-hint"
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
        className={field.select}
      >
        <option value="">Instructions Draft</option>
        {history.data?.versions.map((version) => (
          <option key={version.id} value={version.id}>
            {`v${String(version.number)}${version.id === history.data.current_version_id ? " (Current)" : ""} · ${version.note}`}
          </option>
        ))}
      </select>
      <p id="playground-instructions-hint" className={field.hint}>
        {hint}
      </p>
    </div>
  );
}

/** Chat with the Agent's Draft, in the page's main column. The answer streams in token by token, and
 * each answer's Trace folds open under it. */
function Playground({ agent, organisationId }: { agent: Agent; organisationId: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [question, setQuestion] = useState("");
  // The Instructions Version questions are asked with; "" for the Instructions Draft.
  const [instructionsVersionId, setInstructionsVersionId] = useState("");
  // Set when a reset has started a new Conversation, until the next question.
  const [wasReset, setWasReset] = useState(false);
  const path = { organisation_id: organisationId, project_id: agent.project_id, agent_id: agent.id };

  function appendToAnswer(update: (answer: ChatMessage) => ChatMessage) {
    setMessages((current) => [...current.slice(0, -1), update(current[current.length - 1] as ChatMessage)]);
  }

  async function ask(question: string) {
    setError(null);
    setWasReset(false);
    setPending(true);
    setMessages((current) => [...current, { role: "user", content: question }, { role: "assistant", content: "" }]);
    try {
      const conversation = conversationId ?? (await startConversation(path)).id;
      setConversationId(conversation);
      const done = await askPlayground(
        { ...path, conversation_id: conversation },
        question,
        instructionsVersionId || null,
        (text) => {
          appendToAnswer((answer) => ({ ...answer, content: answer.content + text }));
        },
        (citation) => {
          appendToAnswer((answer) => ({ ...answer, citations: [...(answer.citations ?? []), citation] }));
        },
        (text) => {
          // The answer leaked the Canary token: what streamed is replaced by the fallback text.
          appendToAnswer((answer) => ({ ...answer, content: text }));
        },
        (text) => {
          // The input Guardrail blocked the question: the refusal text is the whole reply.
          appendToAnswer((answer) => ({ ...answer, content: text, refused: true }));
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
    <section aria-labelledby="playground-heading" className="mx-auto flex w-full max-w-[720px] min-w-0 flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h2 id="playground-heading" className={text.heading}>
          Playground
        </h2>
        <p className={text.muted}>Chat with this Draft. Playground Conversations are recorded but kept out of metrics.</p>
      </div>
      <div className="flex flex-wrap items-start gap-3">
        <InstructionsPicker
          organisationId={organisationId}
          projectId={agent.project_id}
          value={instructionsVersionId}
          onChange={setInstructionsVersionId}
        />
        <div className="flex items-center gap-3 pt-7">
          <button
            type="button"
            disabled={pending}
            onClick={() => {
              void reset();
            }}
            className={button.quiet}
          >
            Reset conversation
          </button>
          <p role="status" className={text.small}>
            {wasReset ? "Started a new conversation." : ""}
          </p>
        </div>
      </div>
      <ol aria-label="Playground messages" aria-live="polite" className="flex flex-col gap-6">
        {messages.map((message, index) =>
          message.role === "user" ? (
            <li
              key={index}
              aria-label="You"
              className="max-w-[85%] self-end rounded-[18px] border border-line bg-surface px-4 py-3 text-[15px] whitespace-pre-wrap text-ink"
            >
              {message.content}
            </li>
          ) : (
            <li key={index} aria-label={agent.name} className="flex gap-3">
              <span
                aria-hidden="true"
                className="flex size-8 shrink-0 items-center justify-center rounded-full bg-accent-soft text-sm font-semibold text-accent-ink"
              >
                {agent.name.charAt(0).toUpperCase()}
              </span>
              <div className="flex min-w-0 flex-1 flex-col gap-2">
                <p className="text-base whitespace-pre-wrap text-ink">{message.content}</p>
                {message.refused && <p className="text-xs font-medium text-flag">Blocked by the input Guardrail: the model wasn&apos;t asked.</p>}
                {message.citations && <Sources citations={message.citations} organisationId={organisationId} projectId={agent.project_id} />}
                {message.instructions && <p className={text.small}>{message.instructions}</p>}
                {message.messageId && conversationId && (
                  <TraceFold summary={message.usage as string}>
                    <PlaygroundTrace path={{ ...path, conversation_id: conversationId, message_id: message.messageId }} />
                  </TraceFold>
                )}
              </div>
            </li>
          ),
        )}
      </ol>
      <FormError message={agentFailure(error)} />
      <form
        aria-label="Ask the Draft"
        onSubmit={onSubmit}
        className="flex items-end gap-2 rounded-[26px] border border-line bg-surface py-1.5 pr-1.5 pl-4 focus-within:border-accent has-[textarea:focus]:outline-2 has-[textarea:focus]:outline-offset-2 has-[textarea:focus]:outline-accent"
      >
        <label htmlFor="question" className="sr-only">
          Question
        </label>
        <textarea
          id="question"
          name="question"
          rows={1}
          maxLength={4000}
          placeholder="Ask the Draft a question"
          value={question}
          onChange={(event) => {
            setQuestion(event.target.value);
          }}
          className="min-h-9 flex-1 resize-none bg-transparent py-2 text-[15px] text-ink placeholder:text-muted focus:outline-none"
        />
        <button type="submit" disabled={pending} className={button.primary}>
          {pending ? "Answering…" : "Send"}
        </button>
      </form>
    </section>
  );
}

/** Asks before archiving: the Agent leaves the Agents list and the Playground turns off. */
function ArchiveDialog({ agent, organisationId, onDone }: { agent: Agent; organisationId: string; onDone: (error: Error | null) => void }) {
  const archive = useArchiveOrRestoreAgent(organisationId, agent.project_id, "archive");
  return (
    <ConfirmDialog
      open
      title={`Archive ${agent.name}?`}
      confirmLabel={`Yes, archive ${agent.name}`}
      destructive
      busy={archive.isPending}
      onConfirm={() => {
        archive.mutate(agent.id, {
          onSettled: (_data, error) => {
            onDone(error);
          },
        });
      }}
      onCancel={() => {
        onDone(null);
      }}
    >
      {agent.name} will be hidden from the Agents list and the Playground will be off. Its Draft and Conversations are kept. An Owner can
      restore it.
    </ConfirmDialog>
  );
}

/** Asks before the Draft's unpublished changes are discarded for the Live Version's settings. */
function DiscardDialog({
  agent,
  organisationId,
  onReplaced,
  onDone,
}: {
  agent: Agent;
  organisationId: string;
  onReplaced: () => void;
  onDone: (error: Error | null) => void;
}) {
  const replace = useReplaceDraft(organisationId, agent.project_id, agent.id);
  const live = agent.live_version as NonNullable<Agent["live_version"]>;
  return (
    <ConfirmDialog
      open
      title="Discard the Draft?"
      confirmLabel="Yes, discard the changes"
      destructive
      busy={replace.isPending}
      onConfirm={() => {
        replace.mutate(
          { versionId: "live", baseRevision: agent.draft_revision },
          {
            onSuccess: onReplaced,
            onSettled: (_data, error) => {
              onDone(error);
            },
          },
        );
      }}
      onCancel={() => {
        onDone(null);
      }}
    >
      The Draft&apos;s unpublished changes will be lost, and it goes back to the settings of the Live Version (v{live.number}).
    </ConfirmDialog>
  );
}

/** Owners only, on an archived Agent: deletion is confirmed by typing the Agent's name exactly. */
function DeleteDialog({ agent, organisationId, onDone }: { agent: Agent; organisationId: string; onDone: () => void }) {
  const remove = useDeleteAgent(organisationId, agent.project_id, agent.id);
  const navigate = useNavigate();
  const [typed, setTyped] = useState("");
  const title = `Delete ${agent.name} permanently`;
  const ready = typed === agent.name && !remove.isPending;

  function confirm() {
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
    <ConfirmDialog
      open
      title={title}
      confirmLabel={title}
      destructive
      busy={remove.isPending}
      confirmDisabled={!ready}
      onConfirm={confirm}
      onCancel={onDone}
      body={
        <form
          aria-label={title}
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (ready) confirm();
          }}
        >
          <FormError message={agentFailure(remove.error)} />
          <div>
            <label htmlFor="delete-agent-name" className={field.label}>
              Type {agent.name} to confirm
            </label>
            <input
              id="delete-agent-name"
              autoComplete="off"
              className={field.input}
              value={typed}
              onChange={(event) => {
                setTyped(event.target.value);
              }}
            />
          </div>
        </form>
      }
    >
      Deleting {agent.name} removes its Draft and Conversations for good. This can&apos;t be undone.
    </ConfirmDialog>
  );
}

function ArchivedAgentNotice({ agent, organisationId, isOwner }: { agent: Agent; organisationId: string; isOwner: boolean }) {
  const restore = useArchiveOrRestoreAgent(organisationId, agent.project_id, "restore");
  return (
    <div role="status" aria-label="Archived" className="space-y-2 rounded-2xl border border-flag bg-flag-soft p-4 text-sm text-flag">
      <p>
        This Agent is archived. It is hidden from the Agents list and the Playground is off.{" "}
        {isOwner ? "Restore it to use it again." : "Only Owners can restore it."}
      </p>
      <FormError message={agentFailure(restore.error)} />
      {isOwner && (
        <button
          type="button"
          className={button.secondary}
          disabled={restore.isPending}
          onClick={() => {
            restore.mutate(agent.id);
          }}
        >
          Restore {agent.name}
        </button>
      )}
    </div>
  );
}

type Confirming = "archive" | "discard" | "delete" | null;

/**
 * The Agent's header: its name with its Live, Draft and alert badges, and a ⋯ menu of the rare
 * actions: Discard Draft (while the Draft differs from the Live Version) and Archive, or, on an
 * archived Agent, permanent deletion (Owners only). Each asks first in a `ConfirmDialog`.
 */
function AgentHeader({ agent, organisationId, isOwner, onReplaced }: { agent: Agent; organisationId: string; isOwner: boolean; onReplaced: () => void }) {
  const headingId = useId();
  const [confirming, setConfirming] = useState<Confirming>(null);
  // Why the last archive or discard was refused, shown under the header.
  const [refusal, setRefusal] = useState<{ action: "archive" | "discard"; error: Error } | null>(null);
  const archived = agent.archived_at !== null;
  const actions: MenuItem[] = [];
  if (!archived && agent.live_version && agent.has_unpublished_changes) actions.push({ label: "Discard Draft", onSelect: () => { setConfirming("discard"); } });
  if (!archived) actions.push({ label: "Archive", onSelect: () => { setConfirming("archive"); } });
  if (archived && isOwner) actions.push({ label: "Delete permanently", danger: true, onSelect: () => { setConfirming("delete"); } });
  const finished = (action: "archive" | "discard") => (error: Error | null) => {
    setConfirming(null);
    setRefusal(error ? { action, error } : null);
  };

  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-2.5">
          <h2 id={headingId} className="text-2xl font-medium tracking-[-0.01em] text-ink">
            {agent.name}
          </h2>
          <LiveStatus agent={agent} />
        </div>
        <div className="flex items-center gap-2">
          <AgentAnalyticsLink organisationId={organisationId} projectId={agent.project_id} agentId={agent.id} />
          {actions.length > 0 && (
            <Menu
              label={<Icon name="more" />}
              triggerLabel="More Agent actions"
              menuLabel="Agent actions"
              align="end"
              triggerClassName={button.icon}
              items={actions}
            />
          )}
        </div>
      </div>
      {!agent.live_version && <p className={text.muted}>Visitors can&apos;t use it until you publish it.</p>}
      {refusal && (
        <FormError message={refusal.action === "archive" ? agentFailure(refusal.error) : draftChangeFailure(refusal.error)} />
      )}
      {confirming === "archive" && <ArchiveDialog agent={agent} organisationId={organisationId} onDone={finished("archive")} />}
      {confirming === "discard" && (
        <DiscardDialog agent={agent} organisationId={organisationId} onReplaced={onReplaced} onDone={finished("discard")} />
      )}
      {confirming === "delete" && (
        <DeleteDialog
          agent={agent}
          organisationId={organisationId}
          onDone={() => {
            setConfirming(null);
          }}
        />
      )}
    </section>
  );
}

/** The top bar's side of the Agent page: the Draft's Saved state, History and Publish. */
function AgentTopBar({ agent, organisationId, draftStatus }: { agent: Agent; organisationId: string; draftStatus: string | null }) {
  const [publishing, setPublishing] = useState(false);
  const close = useCallback(() => {
    setPublishing(false);
  }, []);
  return (
    <TopBarActions>
      {draftStatus !== null && (
        <p role="status" aria-label="Draft status" className="flex items-center gap-1.5 text-sm text-muted">
          {draftStatus === "All changes saved" && <Icon name="check" size={14} />}
          {draftStatus}
        </p>
      )}
      <Link
        to="/organisations/$organisationId/projects/$projectId/agents/$agentId/versions"
        params={{ organisationId, projectId: agent.project_id, agentId: agent.id }}
        className={button.ghost}
      >
        <Icon name="history" size={16} />
        History
      </Link>
      {agent.archived_at === null && (
        <>
          <button
            type="button"
            className={button.primary}
            onClick={() => {
              setPublishing(true);
            }}
          >
            Publish
          </button>
          <Dialog open={publishing} title={`Publish ${agent.name}`} onClose={close}>
            <PublishAgent agent={agent} organisationId={organisationId} />
          </Dialog>
        </>
      )}
    </TopBarActions>
  );
}

/**
 * One Agent: its header, the top bar's Saved state, History and Publish, and the view the breadcrumb
 * chose (Playground, Versions, Embed & limits). An archived Agent's Draft is read only, without
 * the Playground, and an Owner can restore it.
 */
export function AgentPage() {
  const { organisationId, isOwner } = useOrganisationRole();
  const { projectId, agentId } = useAgentParams();
  const agent = useAgent(organisationId, projectId, agentId);
  // Moves on whenever the Draft is replaced (discarded, started from a Version, or someone
  // else's loaded), so the editor starts again from the new Draft.
  const [generation, setGeneration] = useState(0);
  const replaced = useCallback(() => {
    setGeneration((current) => current + 1);
  }, []);
  const [draftStatus, setDraftStatus] = useState<string | null>(null);

  if (agent.isPending) return <Skeleton label="Loading the Agent" />;
  if (agent.isError) {
    return (
      <EmptyState
        icon="agents"
        title="Agent not found"
        description="It doesn't exist in this Project, or it was deleted."
        action={
          <Link to="/organisations/$organisationId/projects/$projectId/agents" params={{ organisationId, projectId }} className={button.secondary}>
            All Agents
          </Link>
        }
      />
    );
  }
  const archived = agent.data.archived_at !== null;
  const view: AgentView = { agent: agent.data, organisationId, isOwner, generation, onReplaced: replaced, onDraftStatus: setDraftStatus };

  return (
    <div className="flex flex-col gap-6">
      <AgentTopBar key={agent.data.id} agent={agent.data} organisationId={organisationId} draftStatus={draftStatus} />
      <AgentHeader key={`header-${agent.data.id}`} agent={agent.data} organisationId={organisationId} isOwner={isOwner} onReplaced={replaced} />
      {archived && <ArchivedAgentNotice agent={agent.data} organisationId={organisationId} isOwner={isOwner} />}
      <AgentViewContext.Provider value={view}>
        <Outlet />
      </AgentViewContext.Provider>
    </div>
  );
}

/** The Playground view: the Playground in the main column, the Draft's configuration beside it. */
export function AgentPlaygroundView() {
  const { agent, organisationId, generation, onReplaced, onDraftStatus } = useAgentView();
  const archived = agent.archived_at !== null;
  return (
    <div className="flex flex-wrap items-start gap-8">
      <div className="flex min-w-0 flex-[999_1_480px] flex-col">
        {archived ? (
          <Notice tone="info">The Playground is off while the Agent is archived.</Notice>
        ) : (
          <Playground key={`playground-${agent.id}`} agent={agent} organisationId={organisationId} />
        )}
      </div>
      <aside aria-label="Configuration" className={`${surface.card} min-w-0 flex-[1_1_360px] overflow-hidden lg:max-w-[420px]`}>
        <DraftEditor
          key={`${agent.id}-${String(archived)}-${String(generation)}`}
          agent={agent}
          organisationId={organisationId}
          onReplaced={onReplaced}
          onStatus={onDraftStatus}
        />
      </aside>
    </div>
  );
}

/** The Versions view: the Live History timeline, then every Version with From/To compare. */
export function AgentVersionsView() {
  const { agent, organisationId, onReplaced } = useAgentView();
  return (
    <div className="flex flex-col gap-6">
      <LiveHistory key={`live-history-${agent.id}`} agent={agent} organisationId={organisationId} archived={agent.archived_at !== null} />
      <AgentVersions agent={agent} organisationId={organisationId} onReplaced={onReplaced} />
    </div>
  );
}

/** The Embed & limits view: the snippet, the Operational Settings and the Theme override, as cards. */
export function AgentEmbedView() {
  const { agent, organisationId, isOwner } = useAgentView();
  if (agent.archived_at !== null) {
    return <Notice tone="info">An archived Agent can&apos;t be embedded. An Owner can restore it.</Notice>;
  }
  return (
    <div className="flex flex-col gap-6">
      <AgentEmbed key={`embed-${agent.id}`} agent={agent} organisationId={organisationId} />
      <AgentBranding key={`branding-${agent.id}`} agent={agent} organisationId={organisationId} isOwner={isOwner} />
    </div>
  );
}
