import type { Schemas } from "@studio/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";
import { ProjectRequestError } from "./projects";

export type EvaluationCase = Schemas["CaseOut"];
export type EvaluationCaseFields = Schemas["CaseIn"];
export type EvaluationRun = Schemas["RunOut"];
export type EvaluationRunResults = Schemas["RunResultsOut"];
export type EvaluationCaseResult = Schemas["CaseResultOut"];

/** How often the Studio reads a Run again while it is queued or running. */
export const RUN_POLL_MS = 1500;

/** Whether the Run is still to finish: queued or running. */
export function inProgress(run: { status: string }): boolean {
  return run.status === "queued" || run.status === "running";
}

function failed(response: Response, error: unknown): ProjectRequestError {
  const detail = (error as { detail?: unknown }).detail;
  return new ProjectRequestError(response.status, typeof detail === "string" ? detail : undefined);
}

/** What to tell the Editor about a refused evaluation request: the API's reason, when it gives one. */
export function evaluationFailure(error: Error | null): string | undefined {
  if (error === null) return undefined;
  if (error instanceof ProjectRequestError && error.detail) return error.detail;
  return "Something went wrong. Try again.";
}

type AgentPath = { organisation_id: string; project_id: string; agent_id: string };

const evaluationKey = (path: AgentPath) => ["evaluation", path.organisation_id, path.project_id, path.agent_id] as const;
const casesKey = (path: AgentPath) => [...evaluationKey(path), "cases"] as const;
const runsKey = (path: AgentPath) => [...evaluationKey(path), "runs"] as const;

/** The Agent's Evaluation Set, oldest case first. */
export function useEvaluationCases(path: AgentPath) {
  return useQuery({
    queryKey: casesKey(path),
    queryFn: async (): Promise<EvaluationCase[]> => {
      const { data, error, response } = await api.GET(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/evaluation/cases",
        { params: { path } },
      );
      if (!data) throw failed(response, error);
      return data;
    },
  });
}

/** Adds a case, or with `caseId` replaces that case's question and expectations. */
export function useSaveEvaluationCase(path: AgentPath, caseId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (fields: EvaluationCaseFields): Promise<EvaluationCase> => {
      const saving =
        caseId === null
          ? api.POST(
              "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/evaluation/cases",
              { params: { path }, body: fields },
            )
          : api.PUT(
              "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/evaluation/cases/{case_id}",
              { params: { path: { ...path, case_id: caseId } }, body: fields },
            );
      const { data, error, response } = await saving;
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: casesKey(path) }),
  });
}

export function useDeleteEvaluationCase(path: AgentPath) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (caseId: string): Promise<void> => {
      const { error, response } = await api.DELETE(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/evaluation/cases/{case_id}",
        { params: { path: { ...path, case_id: caseId } } },
      );
      if (!response.ok) throw failed(response, error);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: casesKey(path) }),
  });
}

/** The Agent's Runs, newest first, read again while one is in progress. */
export function useEvaluationRuns(path: AgentPath) {
  return useQuery({
    queryKey: runsKey(path),
    queryFn: async (): Promise<EvaluationRun[]> => {
      const { data, error, response } = await api.GET(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/evaluation/runs",
        { params: { path } },
      );
      if (!data) throw failed(response, error);
      return data;
    },
    refetchInterval: (query) => ((query.state.data ?? []).some(inProgress) ? RUN_POLL_MS : false),
  });
}

/** Starts a Run of the set: the Draft alone, with the Current Instructions Version. */
export function useStartEvaluationRun(path: AgentPath) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<EvaluationRun> => {
      const { data, error, response } = await api.POST(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/evaluation/runs",
        { params: { path } },
      );
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: runsKey(path) }),
  });
}

/** A Run with each case's answers, Verdicts and Traces, read again while it is in progress. */
export function useEvaluationRunResults(path: AgentPath, runId: string) {
  return useQuery({
    queryKey: [...runsKey(path), runId, "results"],
    queryFn: async (): Promise<EvaluationRunResults> => {
      const { data, error, response } = await api.GET(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/evaluation/runs/{run_id}/results",
        { params: { path: { ...path, run_id: runId } } },
      );
      if (!data) throw failed(response, error);
      return data;
    },
    refetchInterval: (query) => (query.state.data && inProgress(query.state.data.run) ? RUN_POLL_MS : false),
  });
}
