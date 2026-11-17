import type { Schemas } from "@studio/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";
import { ProjectRequestError } from "./projects";

export type Suggestion = Schemas["SuggestionOut"];
export type SuggestionSummary = Schemas["SuggestionSummaryOut"];
export type SuggestedChange = Schemas["SuggestedChangeOut"];
export type SuggestionEvidence = Schemas["EvidenceOut"];
export type SuggestionRange = { range_start: string; range_end: string };

/** How often the Studio reads a Suggestion run again while it is in progress. */
export const SUGGESTION_POLL_MS = 1500;
/** The range a run reads unless another is chosen: the last 14 UTC days, today included. */
export const DEFAULT_RANGE_DAYS = 14;

/** Whether the Suggestion run is still to finish: queued, gathering, proposing or checking. */
export function suggestionInProgress(suggestion: { status: string }): boolean {
  return ["queued", "gathering", "proposing", "checking"].includes(suggestion.status);
}

/** The default range, as UTC days (YYYY-MM-DD): the last 14, ending `today`. */
export function defaultRange(today: Date): SuggestionRange {
  const end = today.toISOString().slice(0, 10);
  const start = new Date(today.getTime() - (DEFAULT_RANGE_DAYS - 1) * 86_400_000).toISOString().slice(0, 10);
  return { range_start: start, range_end: end };
}

type AgentPath = {
  organisation_id: string;
  project_id: string;
  agent_id: string;
};

function failed(response: Response, error: unknown): ProjectRequestError {
  const detail = (error as { detail?: unknown }).detail;
  return new ProjectRequestError(response.status, typeof detail === "string" ? detail : undefined);
}

const suggestionsKey = (path: AgentPath) =>
  ["suggestions", path.organisation_id, path.project_id, path.agent_id] as const;

/** The Agent's Suggestions, newest first, read again while one is in progress. */
export function useSuggestions(path: AgentPath) {
  return useQuery({
    queryKey: suggestionsKey(path),
    queryFn: async (): Promise<SuggestionSummary[]> => {
      const { data, error, response } = await api.GET(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/suggestions",
        { params: { path } },
      );
      if (!data) throw failed(response, error);
      return data;
    },
    refetchInterval: (query) =>
      (query.state.data ?? []).some(suggestionInProgress) ? SUGGESTION_POLL_MS : false,
  });
}

/** One Suggestion with its changes and evidence, read again while its run is in progress. */
export function useSuggestion(path: AgentPath, suggestionId: string) {
  return useQuery({
    queryKey: [...suggestionsKey(path), suggestionId],
    queryFn: async (): Promise<Suggestion> => {
      const { data, error, response } = await api.GET(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/suggestions/{suggestion_id}",
        { params: { path: { ...path, suggestion_id: suggestionId } } },
      );
      if (!data) throw failed(response, error);
      return data;
    },
    refetchInterval: (query) =>
      query.state.data && suggestionInProgress(query.state.data) ? SUGGESTION_POLL_MS : false,
  });
}

export function useStartSuggestionRun(path: AgentPath) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (range: SuggestionRange): Promise<Suggestion> => {
      const { data, error, response } = await api.POST(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/suggestions",
        { params: { path }, body: range },
      );
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: suggestionsKey(path) }),
  });
}
