import type { Schemas } from "@studio/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";
import { ProjectRequestError } from "./projects";

export type EvaluationCase = Schemas["CaseOut"];
export type EvaluationCaseFields = Schemas["NewCaseIn"];
export type EvaluationPrefill = Schemas["PrefillOut"];
/** The set's filters: search text, an expectation kind, the Stale flag and the latest result; "" for any. */
export type EvaluationCaseFilters = {
  q: string;
  kind: "" | "expected_source" | "reference_answer" | "fallback";
  stale: "" | "true" | "false";
  result: "" | "pass" | "fail" | "unsteady" | "error" | "not_run";
};
export const NO_CASE_FILTERS: EvaluationCaseFilters = {
  q: "",
  kind: "",
  stale: "",
  result: "",
};

/** The most cases an Evaluation Set holds. */
export const CASES_MAX = 200;
export type EvaluationExpectedSource = Schemas["ExpectedSourceOut"];
export type EvaluationRun = Schemas["RunOut"];
export type EvaluationRunResults = Schemas["RunResultsOut"];
export type EvaluationCaseResult = Schemas["CaseResultOut"];
export type EvaluationCaseSide = Schemas["CaseSideOut"];
export type EvaluationRunSide = Schemas["RunSideOut"];
export type EvaluationRunChoice = Schemas["RunIn"];
export type EvaluationEstimate = Schemas["EstimateOut"];
export type EvaluationPublishSummary = Schemas["PublishSummaryOut"];
export type EvaluationRegression = Schemas["SummaryRegressionOut"];

/** How often the Studio reads a Run again while it is queued or running. */
export const RUN_POLL_MS = 1500;

/** Whether the Run is still to finish: queued or running. */
export function inProgress(run: { status: string }): boolean {
  return run.status === "queued" || run.status === "running";
}

function failed(response: Response, error: unknown): ProjectRequestError {
  const detail = (error as { detail?: unknown }).detail;
  return new ProjectRequestError(
    response.status,
    typeof detail === "string" ? detail : undefined,
  );
}

/** What to tell the Editor about a refused evaluation request: the API's reason, when it gives one. */
export function evaluationFailure(error: Error | null): string | undefined {
  if (error === null) return undefined;
  if (error instanceof ProjectRequestError && error.detail) return error.detail;
  return "Something went wrong. Try again.";
}

type AgentPath = {
  organisation_id: string;
  project_id: string;
  agent_id: string;
};

const evaluationKey = (path: AgentPath) =>
  ["evaluation", path.organisation_id, path.project_id, path.agent_id] as const;
const casesKey = (path: AgentPath) =>
  [...evaluationKey(path), "cases"] as const;
const runsKey = (path: AgentPath) => [...evaluationKey(path), "runs"] as const;
const summaryKey = (path: AgentPath) =>
  [...evaluationKey(path), "publish-summary"] as const;

/** The Agent's Evaluation Set, oldest case first; with `filters`, only the cases matching them. */
export function useEvaluationCases(
  path: AgentPath,
  filters: EvaluationCaseFilters = NO_CASE_FILTERS,
) {
  const query = {
    ...(filters.q.trim() !== "" && { q: filters.q.trim() }),
    ...(filters.kind !== "" && { kind: filters.kind }),
    ...(filters.stale !== "" && { stale: filters.stale === "true" }),
    ...(filters.result !== "" && { result: filters.result }),
  };
  return useQuery({
    queryKey: [...casesKey(path), query],
    queryFn: async (): Promise<EvaluationCase[]> => {
      const { data, error, response } = await api.GET(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/evaluation/cases",
        { params: { path, query } },
      );
      if (!data) throw failed(response, error);
      return data;
    },
  });
}

/** A new case prefilled from one of the Agent's replies: the question it answered and the passages it cited. */
export function useEvaluationPrefill(path: AgentPath, messageId: string) {
  return useQuery({
    queryKey: [...evaluationKey(path), "prefill", messageId],
    queryFn: async (): Promise<EvaluationPrefill> => {
      const { data, error, response } = await api.GET(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/evaluation/messages/{message_id}/prefill",
        { params: { path: { ...path, message_id: messageId } } },
      );
      if (!data) throw failed(response, error);
      return data;
    },
    retry: false,
  });
}

/** Copies cases of another Agent of the Project into this Agent's set, as independent copies. */
export function useCopyEvaluationCases(path: AgentPath) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (choice: {
      agent_id: string;
      case_ids: string[];
    }): Promise<EvaluationCase[]> => {
      const { data, error, response } = await api.POST(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/evaluation/cases/copy",
        { params: { path }, body: choice },
      );
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: casesKey(path) }),
  });
}

/** Adds a case, or with `caseId` replaces that case's question and expectations (where it came from stays). */
export function useSaveEvaluationCase(path: AgentPath, caseId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (
      fields: EvaluationCaseFields,
    ): Promise<EvaluationCase> => {
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
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: casesKey(path) }),
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
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: casesKey(path) }),
  });
}

/**
 * The Agent's Runs, newest first, read again while one is in progress. When a Run that was in
 * progress has finished, the Evaluation Set is read again too: its cases' latest results come
 * from that Run.
 */
export function useEvaluationRuns(path: AgentPath) {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: runsKey(path),
    queryFn: async (): Promise<EvaluationRun[]> => {
      const { data, error, response } = await api.GET(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/evaluation/runs",
        { params: { path } },
      );
      if (!data) throw failed(response, error);
      const before = queryClient.getQueryData<EvaluationRun[]>(runsKey(path)) ?? [];
      const wasRunning = new Set(before.filter(inProgress).map((run) => run.id));
      if (data.some((run) => wasRunning.has(run.id) && !inProgress(run))) {
        void queryClient.invalidateQueries({ queryKey: casesKey(path) });
      }
      return data;
    },
    refetchInterval: (query) =>
      (query.state.data ?? []).some(inProgress) ? RUN_POLL_MS : false,
  });
}

/** The estimated Cost of a Run with these choices, shown before it starts; `null` asks nothing. */
export function useEvaluationEstimate(
  path: AgentPath,
  choice: EvaluationRunChoice | null,
) {
  return useQuery({
    queryKey: [...evaluationKey(path), "estimate", choice],
    queryFn: async (): Promise<EvaluationEstimate> => {
      const { data, error, response } = await api.POST(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/evaluation/estimate",
        { params: { path }, body: choice },
      );
      if (!data) throw failed(response, error);
      return data;
    },
    enabled: choice !== null,
    retry: false,
  });
}

/** Starts a Run of the set with the chosen sides and the Draft's Instructions. */
export function useStartEvaluationRun(path: AgentPath) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (choice: EvaluationRunChoice): Promise<EvaluationRun> => {
      const { data, error, response } = await api.POST(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/evaluation/runs",
        { params: { path }, body: choice },
      );
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: runsKey(path) }),
  });
}

/** Cancels a queued or running Run; it stops before its next answer and keeps what it spent. */
export function useCancelEvaluationRun(path: AgentPath) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (runId: string): Promise<EvaluationRun> => {
      const { data, error, response } = await api.POST(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/evaluation/runs/{run_id}/cancel",
        { params: { path: { ...path, run_id: runId } } },
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
    refetchInterval: (query) =>
      query.state.data && inProgress(query.state.data.run)
        ? RUN_POLL_MS
        : false,
  });
}

/**
 * The Evaluation summary for publishing the Draft with `instructionsVersionId` (the Current
 * Instructions Version when `null`). `freshness` (the Live Version and the Draft revision) reads it
 * again whenever either moves on.
 */
export function usePublishSummary(
  path: AgentPath,
  instructionsVersionId: string | null,
  freshness: readonly unknown[],
) {
  return useQuery({
    queryKey: [...summaryKey(path), instructionsVersionId, ...freshness],
    queryFn: async (): Promise<EvaluationPublishSummary> => {
      const { data, error, response } = await api.GET(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/evaluation/publish-summary",
        {
          params: {
            path,
            query:
              instructionsVersionId === null
                ? {}
                : { instructions_version_id: instructionsVersionId },
          },
        },
      );
      if (!data) throw failed(response, error);
      return data;
    },
  });
}

/** One Run, read again while it is in progress; once it has finished, the Publish summary is read again. */
export function useEvaluationRun(path: AgentPath, runId: string | null) {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: [...runsKey(path), runId],
    queryFn: async (): Promise<EvaluationRun> => {
      const { data, error, response } = await api.GET(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/evaluation/runs/{run_id}",
        { params: { path: { ...path, run_id: runId as string } } },
      );
      if (!data) throw failed(response, error);
      if (!inProgress(data))
        await queryClient.invalidateQueries({ queryKey: summaryKey(path) });
      return data;
    },
    enabled: runId !== null,
    refetchInterval: (query) =>
      query.state.data && inProgress(query.state.data) ? RUN_POLL_MS : false,
  });
}

export type RolloutEvaluation = Schemas["RolloutEvaluationOut"];
export type RolloutAgentEvaluation = Schemas["RolloutAgentEvaluationOut"];

const rolloutEvaluationKey = (
  organisationId: string,
  projectId: string,
  instructionsVersionId: string,
) =>
  [
    "rollout-evaluation",
    organisationId,
    projectId,
    instructionsVersionId,
  ] as const;

/** Each active Agent's Rollout evaluation of the Instructions Version, read again while one is running. */
export function useRolloutEvaluation(
  organisationId: string,
  projectId: string,
  instructionsVersionId: string,
) {
  return useQuery({
    queryKey: rolloutEvaluationKey(
      organisationId,
      projectId,
      instructionsVersionId,
    ),
    queryFn: async (): Promise<RolloutEvaluation> => {
      const { data, error, response } = await api.GET(
        "/api/organisations/{organisation_id}/projects/{project_id}/instructions/versions/{instructions_version_id}/evaluation",
        {
          params: {
            path: {
              organisation_id: organisationId,
              project_id: projectId,
              instructions_version_id: instructionsVersionId,
            },
          },
        },
      );
      if (!data) throw failed(response, error);
      return data;
    },
    refetchInterval: (query) =>
      (query.state.data?.agents ?? []).some(
        (agent) => agent.state === "running",
      )
        ? RUN_POLL_MS
        : false,
  });
}

/** Starts a Rollout evaluation of the selected Agents; those without an Evaluation Set are skipped. */
export function useStartRolloutEvaluation(
  organisationId: string,
  projectId: string,
  instructionsVersionId: string,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (agentIds: string[]): Promise<RolloutEvaluation> => {
      const { data, error, response } = await api.POST(
        "/api/organisations/{organisation_id}/projects/{project_id}/instructions/versions/{instructions_version_id}/evaluation",
        {
          params: {
            path: {
              organisation_id: organisationId,
              project_id: projectId,
              instructions_version_id: instructionsVersionId,
            },
          },
          body: { agent_ids: agentIds },
        },
      );
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({
          queryKey: rolloutEvaluationKey(
            organisationId,
            projectId,
            instructionsVersionId,
          ),
        }),
        // The Rollout evaluations are in each Agent's Run history.
        queryClient.invalidateQueries({
          queryKey: ["evaluation", organisationId, projectId],
        }),
      ]),
  });
}
