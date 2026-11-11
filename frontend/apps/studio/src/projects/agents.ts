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

/** A `search` event: the model started a Knowledge Search (Agentic Retrieval Mode). */
export type SearchStarted = { query: string; order: number };

/** The `done` event that ends a streamed Playground answer. */
export type AnswerDone = {
  message_id: string;
  /** The Project Instructions the answer ran with: the Draft, or a Version. */
  instructions_source: "draft" | "version";
  instructions_version_id: string | null;
  instructions_version_number: number | null;
  input_tokens: number;
  output_tokens: number;
  first_token_ms: number;
  latency_ms: number;
  chunks: { chunk_id: string; score: number; rank: number }[];
};

/** "Draft" or "v2": the Project Instructions an answer ran with. */
export function instructionsUsed(used: {
  instructions_source: string | null;
  instructions_version_number: number | null;
}): string {
  return used.instructions_source === "version"
    ? `v${String(used.instructions_version_number)}`
    : "Draft";
}

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
  // A 409, or a 422 with one reason (an Instructions Version not in the Project), says why.
  if (
    error instanceof ProjectRequestError &&
    error.detail &&
    (error.status === 409 || error.status === 422)
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

/** Puts an Agent the API returned into the cache, and refreshes the lists that show it. */
export function useStoreAgent(organisationId: string, projectId: string) {
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

/**
 * A Draft change refused because someone else changed the Draft after the revision it was
 * made on. Carries their latest Draft, so the Editor can load it or save over it.
 */
export class StaleDraftError extends Error {
  constructor(readonly latest: Agent) {
    super("Someone else changed this Draft.");
    this.name = "StaleDraftError";
  }
}

function staleOr(error: unknown): Agent | undefined {
  return (error as { latest?: Agent | null } | undefined)?.latest ?? undefined;
}

/**
 * Saves the Draft made on revision `baseRevision`. A Draft someone has changed since is
 * refused with a `StaleDraftError` instead of being overwritten.
 */
export function useSaveDraft(
  organisationId: string,
  projectId: string,
  agentId: string,
) {
  const store = useStoreAgent(organisationId, projectId);
  return useMutation({
    mutationFn: async ({
      draft,
      baseRevision,
    }: {
      draft: AgentDraft;
      baseRevision: number;
    }): Promise<Agent> => {
      const { data, error, response } = await api.PUT(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/draft",
        {
          params: {
            path: {
              organisation_id: organisationId,
              project_id: projectId,
              agent_id: agentId,
            },
            query: { base_revision: baseRevision },
          },
          body: draft,
        },
      );
      const latest = staleOr(error);
      if (latest) throw new StaleDraftError(latest);
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
 * far when the answer leaked the Canary token; `onRefusal` the Agent's refusal text, the whole
 * reply, when the input Guardrail blocked the question; `onSearch` each Knowledge Search as it
 * starts, in Agentic Retrieval Mode, and `onRetract` that the text streamed so far was not the
 * answer (the model went on to search), so it is cleared. The returned promise resolves with the `done`
 * event once the answer is complete and saved, or rejects with a `ProviderError` when the
 * stream ends with an `error` event because the model provider failed.
 */
export async function askPlayground(
  path: AgentPath & { conversation_id: string },
  question: string,
  /** The Instructions Version to answer with; null for the Instructions Draft. */
  instructionsVersionId: string | null,
  onToken: (text: string) => void,
  onCitation: (citation: Citation) => void,
  onReplace: (text: string) => void,
  onRefusal: (text: string) => void,
  onSearch: (search: SearchStarted) => void,
  onRetract: () => void,
): Promise<AnswerDone> {
  const { data, error, response } = await api.POST(
    "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/playground/conversations/{conversation_id}/messages",
    {
      params: { path },
      body: { content: question, instructions_version_id: instructionsVersionId },
      parseAs: "stream",
    },
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
      if (event.event === "search") onSearch(event.data as SearchStarted);
      if (event.event === "retract") onRetract();
      if (event.event === "token")
        onToken((event.data as { text: string }).text);
      if (event.event === "citation") onCitation(event.data as Citation);
      if (event.event === "replace")
        onReplace((event.data as { text: string }).text);
      if (event.event === "refusal")
        onRefusal((event.data as { text: string }).text);
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

export type AgentDiff = Schemas["AgentDiffOut"];
/** A side of a diff: the Draft, the Live Version, or a Version's ID. */
export type DiffSide = "draft" | "live" | (string & {});

/**
 * What changes from one side to the other. `revision` is the Draft revision it was made on, so
 * a diff involving the Draft is fetched again once the Draft changes.
 */
export function useAgentDiff(
  organisationId: string,
  projectId: string,
  agentId: string,
  sides: { from: DiffSide; to: DiffSide; revision: number },
  enabled = true,
) {
  return useQuery({
    queryKey: [...agentsKey(organisationId, projectId), agentId, "diff", sides],
    enabled,
    queryFn: async (): Promise<AgentDiff> => {
      const { data, error, response } = await api.GET(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/diff",
        {
          params: {
            path: {
              organisation_id: organisationId,
              project_id: projectId,
              agent_id: agentId,
            },
            query: { from: sides.from, to: sides.to },
          },
        },
      );
      if (!data) throw failed(response, error);
      return data;
    },
  });
}

/** The Agent's Versions, newest first, and which is Live. */
/** The Agent's Versions; with `enabled` false, nothing is fetched (no Agent chosen yet). */
export function useAgentVersions(
  organisationId: string,
  projectId: string,
  agentId: string,
  enabled = true,
) {
  return useQuery({
    enabled,
    queryKey: [...agentsKey(organisationId, projectId), agentId, "versions"],
    queryFn: async (): Promise<Schemas["AgentVersionsOut"]> => {
      const { data, error, response } = await api.GET(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/versions",
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

/** What to tell the Editor about a refused Draft change: discarding it or starting it again. */
export function draftChangeFailure(error: Error | null): string | undefined {
  if (error instanceof StaleDraftError)
    return "Someone else changed this Draft since you opened it. Their changes are shown now: review them and try again.";
  if (error instanceof ProjectRequestError && error.status === 422)
    return "That Version names a credential or Tag that no longer exists, so it can't start the Draft.";
  return agentFailure(error);
}

/**
 * Replaces the Draft made on revision `baseRevision`: with the Live Version's configuration
 * (`discard`), or with a Version's (`versionId`). Nothing is published.
 */
export function useReplaceDraft(
  organisationId: string,
  projectId: string,
  agentId: string,
) {
  const store = useStoreAgent(organisationId, projectId);
  return useMutation({
    mutationFn: async ({
      versionId,
      baseRevision,
    }: {
      versionId: "live" | (string & {});
      baseRevision: number;
    }): Promise<Agent> => {
      const path = {
        organisation_id: organisationId,
        project_id: projectId,
        agent_id: agentId,
      };
      const query = { base_revision: baseRevision };
      const { data, error, response } =
        versionId === "live"
          ? await api.POST(
              "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/draft/discard",
              { params: { path, query } },
            )
          : await api.POST(
              "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/draft/from-version",
              { params: { path, query }, body: { version_id: versionId } },
            );
      const latest = staleOr(error);
      if (latest) {
        await store(latest);
        throw new StaleDraftError(latest);
      }
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: store,
  });
}

export type LiveHistoryEntry = Schemas["LiveHistoryEntryOut"];

/** Every change of the Agent's Live Version, newest first. */
export function useLiveHistory(
  organisationId: string,
  projectId: string,
  agentId: string,
) {
  return useQuery({
    queryKey: [...agentsKey(organisationId, projectId), agentId, "live-history"],
    queryFn: async (): Promise<LiveHistoryEntry[]> => {
      const { data, error, response } = await api.GET(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/live-history",
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

/**
 * The Version a revert would make Live again: the one Live when the present Live Version was
 * published. Reverts aren't followed, so reverting twice walks further back. The API applies
 * the same rule and has the final say.
 */
export function revertTarget(
  liveVersionId: string,
  history: LiveHistoryEntry[],
): LiveHistoryEntry["from_version"] {
  const pushed = history.find(
    (entry) =>
      entry.to_version.id === liveVersionId &&
      (entry.action === "publish" || entry.action === "bulk_publish"),
  );
  return pushed?.from_version ?? null;
}

/** Moves the Live Version back one step in the Live History and returns the Version now Live. */
export function useRevertAgent(
  organisationId: string,
  projectId: string,
  agentId: string,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<AgentVersion> => {
      const { data, error, response } = await api.POST(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/revert",
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
    onSettled: () =>
      queryClient.invalidateQueries({
        queryKey: agentsKey(organisationId, projectId),
      }),
  });
}
