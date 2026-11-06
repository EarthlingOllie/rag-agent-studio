import type { Schemas } from "@studio/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";
import { draftFailed } from "./draft";
import { ProjectRequestError } from "./projects";

export type Agent = Schemas["AgentOut"];
export type AgentDraft = Schemas["AgentConfig-Output"];
export type Conversation = Schemas["ConversationOut"];
export type Trace = Schemas["TraceOut"];

/** A `citation` event: the answer cites the Chunk the model was given labelled `label`. */
export type Citation = {
  label: string;
  chunk_id: string;
  document_id: string;
  document_name: string;
  rank: number;
};

/** The `done` event that ends a streamed Playground answer. */
export type AnswerDone = {
  message_id: string;
  input_tokens: number;
  output_tokens: number;
  first_token_ms: number;
  latency_ms: number;
  chunks: { chunk_id: string; score: number; rank: number }[];
};

/** Why the model provider failed, from a Playground stream's `error` event. */
export type ProviderErrorCode =
  | "invalid_key"
  | "rate_limited"
  | "model_unavailable"
  | "provider_error";

/** The provider failed while answering: the stream ended with an `error` event, no answer. */
export class ProviderError extends Error {
  constructor(
    readonly code: ProviderErrorCode,
    message: string,
  ) {
    super(message);
    this.name = "ProviderError";
  }
}

function failed(response: Response, error: unknown): ProjectRequestError {
  const detail = (error as { detail?: unknown }).detail;
  return new ProjectRequestError(
    response.status,
    typeof detail === "string" ? detail : undefined,
  );
}

/** What to tell the Editor about a failed Agent or Playground request. */
export function agentFailure(error: Error | null): string | undefined {
  if (error === null) return undefined;
  if (error instanceof ProviderError) return error.message;
  if (
    error instanceof ProjectRequestError &&
    error.detail &&
    error.status === 409
  )
    return error.detail;
  if (error instanceof ProjectRequestError && error.status === 422)
    return "Check the highlighted settings: a name up to 200 characters, and top-k from 1 to 20.";
  return "Something went wrong. Try again.";
}

const agentsKey = (organisationId: string, projectId: string) =>
  ["agents", organisationId, projectId] as const;
const listsKey = (organisationId: string, projectId: string) =>
  [...agentsKey(organisationId, projectId), "list"] as const;

/** The Project's active Agents, or its archived ones. */
export function useAgents(
  organisationId: string,
  projectId: string,
  archived = false,
) {
  return useQuery({
    queryKey: [...listsKey(organisationId, projectId), { archived }],
    queryFn: async (): Promise<Agent[]> => {
      const { data, error, response } = await api.GET(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents",
        {
          params: {
            path: { organisation_id: organisationId, project_id: projectId },
            query: { archived },
          },
        },
      );
      if (!data) throw failed(response, error);
      return data;
    },
  });
}

export function useAgent(
  organisationId: string,
  projectId: string,
  agentId: string,
) {
  return useQuery({
    queryKey: [...agentsKey(organisationId, projectId), agentId],
    queryFn: async (): Promise<Agent> => {
      const { data, error, response } = await api.GET(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}",
        {
          params: {
            path: {
              organisation_id: organisationId,
              project_id: projectId,
              agent_id: agentId,
            },
          },
        },
      );
      if (!data) throw failed(response, error);
      return data;
    },
  });
}

function useStoreAgent(organisationId: string, projectId: string) {
  const queryClient = useQueryClient();
  return async (agent: Agent) => {
    queryClient.setQueryData(
      [...agentsKey(organisationId, projectId), agent.id],
      agent,
    );
    await queryClient.invalidateQueries({
      queryKey: listsKey(organisationId, projectId),
    });
    await queryClient.invalidateQueries({
      queryKey: ["projects", organisationId],
    });
  };
}

export function useCreateAgent(organisationId: string, projectId: string) {
  const store = useStoreAgent(organisationId, projectId);
  return useMutation({
    mutationFn: async (name: string): Promise<Agent> => {
      const { data, error, response } = await api.POST(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents",
        {
          params: {
            path: { organisation_id: organisationId, project_id: projectId },
          },
          body: { name },
        },
      );
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: store,
  });
}

export function useSaveDraft(
  organisationId: string,
  projectId: string,
  agentId: string,
) {
  const store = useStoreAgent(organisationId, projectId);
  return useMutation({
    mutationFn: async (draft: AgentDraft): Promise<Agent> => {
      const { data, error, response } = await api.PUT(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/draft",
        {
          params: {
            path: {
              organisation_id: organisationId,
              project_id: projectId,
              agent_id: agentId,
            },
          },
          body: draft,
        },
      );
      if (!data) throw draftFailed(response, error);
      return data;
    },
    onSuccess: store,
  });
}

/** Archive (any Member) or restore (Owners) an Agent. */
export function useArchiveOrRestoreAgent(
  organisationId: string,
  projectId: string,
  action: "archive" | "restore",
) {
  const store = useStoreAgent(organisationId, projectId);
  return useMutation({
    mutationFn: async (agentId: string): Promise<Agent> => {
      const path =
        action === "archive"
          ? ("/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/archive" as const)
          : ("/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/restore" as const);
      const { data, error, response } = await api.POST(path, {
        params: {
          path: {
            organisation_id: organisationId,
            project_id: projectId,
            agent_id: agentId,
          },
        },
      });
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: store,
  });
}

/** Permanently delete an archived Agent (Owners), confirmed by its name typed exactly. */
export function useDeleteAgent(
  organisationId: string,
  projectId: string,
  agentId: string,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (confirmName: string): Promise<void> => {
      const { error, response } = await api.DELETE(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}",
        {
          params: {
            path: {
              organisation_id: organisationId,
              project_id: projectId,
              agent_id: agentId,
            },
          },
          body: { confirm_name: confirmName },
        },
      );
      if (!response.ok) throw failed(response, error);
    },
    onSuccess: async () => {
      queryClient.removeQueries({
        queryKey: [...agentsKey(organisationId, projectId), agentId],
      });
      await queryClient.invalidateQueries({
        queryKey: listsKey(organisationId, projectId),
      });
      await queryClient.invalidateQueries({
        queryKey: ["projects", organisationId],
      });
    },
  });
}

type AgentPath = {
  organisation_id: string;
  project_id: string;
  agent_id: string;
};

export async function startConversation(
  path: AgentPath,
): Promise<Conversation> {
  const { data, error, response } = await api.POST(
    "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/playground/conversations",
    { params: { path } },
  );
  if (!data) throw failed(response, error);
  return data;
}

/** One Server-Sent Event: its name and its JSON data. */
type StreamEvent = { event: string; data: unknown };

function parseEvent(block: string): StreamEvent {
  const fields = new Map(
    block.split("\n").map((line) => {
      const at = line.indexOf(": ");
      return [line.slice(0, at), line.slice(at + 2)] as const;
    }),
  );
  // The API sends every event with both fields.
  return {
    event: fields.get("event") as string,
    data: JSON.parse(fields.get("data") as string),
  };
}

/**
 * Asks the Agent's Draft a question. `onToken` receives the answer as it streams in, and
 * `onCitation` each Chunk it cites; `onReplace` the text that replaces everything streamed so
 * far when the answer leaked the Canary token. The returned promise resolves with the `done`
 * event once the answer is complete and saved, or rejects with a `ProviderError` when the
 * stream ends with an `error` event because the model provider failed.
 */
export async function askPlayground(
  path: AgentPath & { conversation_id: string },
  question: string,
  onToken: (text: string) => void,
  onCitation: (citation: Citation) => void,
  onReplace: (text: string) => void,
): Promise<AnswerDone> {
  const { data, error, response } = await api.POST(
    "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/playground/conversations/{conversation_id}/messages",
    { params: { path }, body: { content: question }, parseAs: "stream" },
  );
  if (!response.ok) throw failed(response, error);
  const reader = (data as ReadableStream<Uint8Array>).getReader();
  const decoder = new TextDecoder();
  let buffered = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffered += decoder.decode(value, { stream: true });
    let end = buffered.indexOf("\n\n");
    while (end !== -1) {
      const event = parseEvent(buffered.slice(0, end));
      buffered = buffered.slice(end + 2);
      end = buffered.indexOf("\n\n");
      if (event.event === "token")
        onToken((event.data as { text: string }).text);
      if (event.event === "citation") onCitation(event.data as Citation);
      if (event.event === "replace")
        onReplace((event.data as { text: string }).text);
      if (event.event === "done") return event.data as AnswerDone;
      if (event.event === "error") {
        const { code, message } = event.data as {
          code: ProviderErrorCode;
          message: string;
        };
        throw new ProviderError(code, message);
      }
    }
  }
  throw new Error("The answer ended before it was complete.");
}

type MessagePath = AgentPath & { conversation_id: string; message_id: string };

/** The Trace of one answer, loaded when its drawer opens. */
export function useTrace(path: MessagePath) {
  return useQuery({
    queryKey: ["trace", path.organisation_id, path.message_id],
    queryFn: async (): Promise<Trace> => {
      const { data, error, response } = await api.GET(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/playground/conversations/{conversation_id}/messages/{message_id}/trace",
        { params: { path } },
      );
      if (!data) throw failed(response, error);
      return data;
    },
    retry: false,
  });
}

export type AgentVersion = Schemas["AgentVersionOut"];

/** What to tell the Editor about a publish the API refused. */
export function publishFailure(error: Error | null): string | undefined {
  if (error instanceof ProjectRequestError && error.status === 422)
    return "Add a note of up to 500 characters.";
  return agentFailure(error);
}

/**
 * Publishes the Agent's saved Draft with a note as its next Version, pinning the chosen
 * Instructions Version (the Project's Current Version when none is chosen), and makes it Live.
 */
export function usePublishAgent(
  organisationId: string,
  projectId: string,
  agentId: string,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (
      body: Schemas["PublishAgentRequest"],
    ): Promise<AgentVersion> => {
      const { data, error, response } = await api.POST(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/versions",
        {
          params: {
            path: {
              organisation_id: organisationId,
              project_id: projectId,
              agent_id: agentId,
            },
          },
          body,
        },
      );
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: agentsKey(organisationId, projectId),
      }),
  });
}
