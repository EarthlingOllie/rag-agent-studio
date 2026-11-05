import { Link, useParams } from "@tanstack/react-router";
import { type SubmitEvent, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { type Agent, agentFailure, askPlayground, startConversation, useAgent } from "./agents";
import { DraftEditor } from "./DraftEditor";
import { BUTTON, INPUT, useOrganisationRole } from "./ProjectsPage";

function useAgentParams() {
  return useParams({ from: "/signed-in/organisations/$organisationId/projects/$projectId/agents/$agentId" });
}

type ChatMessage = { role: "user" | "assistant"; content: string; usage?: string };

/** Chat with the Agent's Draft. The answer streams in token by token. */
function Playground({ agent, organisationId }: { agent: Agent; organisationId: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [question, setQuestion] = useState("");
  const path = { organisation_id: organisationId, project_id: agent.project_id, agent_id: agent.id };

  function appendToAnswer(update: (answer: ChatMessage) => ChatMessage) {
    setMessages((current) => [...current.slice(0, -1), update(current[current.length - 1] as ChatMessage)]);
  }

  async function ask(question: string) {
    setError(null);
    setPending(true);
    setMessages((current) => [...current, { role: "user", content: question }, { role: "assistant", content: "" }]);
    try {
      const conversation = conversationId ?? (await startConversation(path)).id;
      setConversationId(conversation);
      const done = await askPlayground({ ...path, conversation_id: conversation }, question, (text) => {
        appendToAnswer((answer) => ({ ...answer, content: answer.content + text }));
      });
      appendToAnswer((answer) => ({
        ...answer,
        usage: `${String(done.input_tokens)} input and ${String(done.output_tokens)} output tokens · ${String(done.latency_ms)} ms`,
      }));
    } catch (failure) {
      setMessages((current) => current.slice(0, -1));
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
      <p className="text-sm text-slate-700">Chat with this Draft. Playground Conversations are recorded but kept out of metrics.</p>
      <ol aria-label="Playground messages" aria-live="polite" className="space-y-2">
        {messages.map((message, index) => (
          <li
            key={index}
            aria-label={message.role === "user" ? "You" : agent.name}
            className={`rounded px-3 py-2 text-sm ${message.role === "user" ? "bg-slate-100" : "border border-slate-200 bg-white"}`}
          >
            <p className="whitespace-pre-wrap">{message.content}</p>
            {message.usage && <p className="mt-1 text-xs text-slate-700">{message.usage}</p>}
          </li>
        ))}
      </ol>
      <FormError message={agentFailure(error)} />
      <form aria-label="Ask the Draft" onSubmit={onSubmit} className="space-y-2">
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
    </section>
  );
}

/** One Agent: its Draft beside the Playground. */
export function AgentPage() {
  const { organisationId } = useOrganisationRole();
  const { projectId, agentId } = useAgentParams();
  const agent = useAgent(organisationId, projectId, agentId);

  let body;
  if (agent.isPending) {
    body = <p role="status">Loading the Agent…</p>;
  } else if (agent.isError) {
    body = <p role="alert">The Agent could not be found.</p>;
  } else {
    body = (
      <>
        <h2 className="text-xl font-semibold">{agent.data.name}</h2>
        <div className="grid gap-8 lg:grid-cols-2">
          <DraftEditor key={agent.data.id} agent={agent.data} organisationId={organisationId} />
          <Playground key={`playground-${agent.data.id}`} agent={agent.data} organisationId={organisationId} />
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
