import type { Schemas } from "@studio/api-client";
import { useMutation, useMutationState, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";
import { rolloutKey } from "./bulk";
import { ProjectRequestError } from "./projects";

function failed(response: Response, error: unknown): ProjectRequestError {
  const detail = (error as { detail?: unknown }).detail;
  return new ProjectRequestError(response.status, typeof detail === "string" ? detail : undefined);
}

/** What to tell the Editor about Instructions the API refused. */
export function instructionsFailure(error: Error | null): string | undefined {
  return error === null ? undefined : draftRefusal(error);
}

function draftRefusal(error: Error): string {
  if (error instanceof ProjectRequestError && error.status === 409 && error.detail) return error.detail;
  if (error instanceof ProjectRequestError && error.status === 422) return "Instructions can be up to 20,000 characters.";
  return "Something went wrong. Try again.";
}

export type DraftInstructions = Schemas["ProjectInstructionsOut"];

/**
 * A save refused because someone else changed the Instructions Draft after the revision it was
 * made on. Carries their latest Draft, so the Editor can load it or save over it.
 */
export class StaleInstructionsError extends Error {
  constructor(readonly latest: DraftInstructions) {
    super("Someone else changed these Instructions.");
    this.name = "StaleInstructionsError";
  }
}

function staleInstructions(error: unknown): DraftInstructions | undefined {
  return (error as { latest?: DraftInstructions | null } | undefined)?.latest ?? undefined;
}

/** A publish whose first step, saving the Draft, was refused; nothing was published. */
export class DraftNotSavedError extends ProjectRequestError {}

/** What to tell the Editor about a publish or revert the API refused. */
export function versionFailure(error: Error | null): string | undefined {
  if (error === null) return undefined;
  if (error instanceof DraftNotSavedError) {
    return `The Draft could not be saved, so nothing was published. ${draftRefusal(error)}`;
  }
  if (error instanceof ProjectRequestError && error.status === 422) return "Add a note of up to 500 characters.";
  return instructionsFailure(error);
}

export type InstructionsVersion = Schemas["InstructionsVersionOut"];
export type InstructionsHistory = Schemas["InstructionsHistoryOut"];
export type InstructionsReverted = Schemas["InstructionsRevertOut"];

const instructionsKey = (organisationId: string, projectId: string) => ["instructions", organisationId, projectId] as const;

/** The Project Instructions Draft: the markdown every Agent in the Project follows, and its revision. */
export function useInstructions(organisationId: string, projectId: string) {
  return useQuery({
    queryKey: instructionsKey(organisationId, projectId),
    queryFn: async (): Promise<DraftInstructions> => {
      const { data, error, response } = await api.GET("/api/organisations/{organisation_id}/projects/{project_id}/instructions", {
        params: { path: { organisation_id: organisationId, project_id: projectId } },
      });
      if (!data) throw failed(response, error);
      return data;
    },
  });
}

type InstructionsPath = { organisation_id: string; project_id: string };

/**
 * Saves the Draft made on revision `baseRevision`. A Draft someone has changed since is
 * refused with a `StaleInstructionsError` instead of being overwritten.
 */
async function saveDraft(path: InstructionsPath, markdown: string, baseRevision: number): Promise<DraftInstructions> {
  const { data, error, response } = await api.PUT("/api/organisations/{organisation_id}/projects/{project_id}/instructions", {
    params: { path, query: { base_revision: baseRevision } },
    body: { markdown },
  });
  const latest = staleInstructions(error);
  if (latest) throw new StaleInstructionsError(latest);
  if (!data) throw failed(response, error);
  return data;
}

/** Puts the Instructions Draft the API returned into the cache. */
export function useStoreInstructions(organisationId: string, projectId: string) {
  const queryClient = useQueryClient();
  return (draft: DraftInstructions) => {
    queryClient.setQueryData(instructionsKey(organisationId, projectId), draft);
  };
}

export function useSaveInstructions(organisationId: string, projectId: string) {
  const store = useStoreInstructions(organisationId, projectId);
  return useMutation({
    mutationFn: ({ markdown, baseRevision }: { markdown: string; baseRevision: number }) =>
      saveDraft({ organisation_id: organisationId, project_id: projectId }, markdown, baseRevision),
    onSuccess: store,
  });
}

const versionsKey = (organisationId: string, projectId: string) => ["instructions-versions", organisationId, projectId] as const;

/** Publishes and reverts share this key prefix, so the Studio can tell which happened last. */
const changeKey = (organisationId: string, projectId: string) => ["instructions-change", organisationId, projectId] as const;

/** Whether the publish or revert submitted at `submittedAt` is the latest one for the Project, so only its outcome shows. */
export function useIsLatestInstructionsChange(organisationId: string, projectId: string, submittedAt: number): boolean {
  const submitted = useMutationState({
    filters: { mutationKey: changeKey(organisationId, projectId) },
    select: (mutation) => mutation.state.submittedAt,
  });
  return submittedAt === Math.max(0, ...submitted);
}

/** The Instructions Versions, newest first, and which one is Current. */
export function useInstructionsVersions(organisationId: string, projectId: string) {
  return useQuery({
    queryKey: versionsKey(organisationId, projectId),
    queryFn: async (): Promise<InstructionsHistory> => {
      const { data, error, response } = await api.GET("/api/organisations/{organisation_id}/projects/{project_id}/instructions/versions", {
        params: { path: { organisation_id: organisationId, project_id: projectId } },
      });
      if (!data) throw failed(response, error);
      return data;
    },
  });
}

/** Saves the Draft as written, then publishes it with a note as the next Version, which becomes Current. */
export function usePublishInstructions(organisationId: string, projectId: string) {
  const queryClient = useQueryClient();
  const path = { organisation_id: organisationId, project_id: projectId };
  return useMutation({
    mutationKey: [...changeKey(organisationId, projectId), "publish"],
    mutationFn: async ({
      markdown,
      note,
      baseRevision,
      onSaved,
    }: {
      markdown: string;
      note: string;
      baseRevision: number;
      /** Told the Draft's new revision once it is saved, before it is published. */
      onSaved: (revision: number) => void;
    }): Promise<InstructionsVersion> => {
      let saved;
      try {
        saved = await saveDraft(path, markdown, baseRevision);
      } catch (refused) {
        if (refused instanceof StaleInstructionsError) throw refused;
        const { status, detail } = refused as ProjectRequestError;
        throw new DraftNotSavedError(status, detail);
      }
      queryClient.setQueryData(instructionsKey(organisationId, projectId), saved);
      onSaved(saved.revision);
      const { data, error, response } = await api.POST("/api/organisations/{organisation_id}/projects/{project_id}/instructions/versions", {
        params: { path },
        body: { note },
      });
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: () => {
      // Which Agents are behind changes too; the outcome shows without waiting for it.
      void queryClient.invalidateQueries({ queryKey: rolloutKey(organisationId, projectId) });
      return queryClient.invalidateQueries({ queryKey: versionsKey(organisationId, projectId) });
    },
  });
}

/** Moves the Current Version back to the one that was Current before it. The Draft is unchanged. */
export function useRevertInstructions(organisationId: string, projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...changeKey(organisationId, projectId), "revert"],
    mutationFn: async (): Promise<InstructionsReverted> => {
      const { data, error, response } = await api.POST("/api/organisations/{organisation_id}/projects/{project_id}/instructions/revert", {
        params: { path: { organisation_id: organisationId, project_id: projectId } },
      });
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: () => {
      // Which Agents are behind changes too; the outcome shows without waiting for it.
      void queryClient.invalidateQueries({ queryKey: rolloutKey(organisationId, projectId) });
      return queryClient.invalidateQueries({ queryKey: versionsKey(organisationId, projectId) });
    },
  });
}

export type InstructionsDiff = Schemas["InstructionsDiffOut"];

/**
 * The line diff of the Instructions from one side to the other: the Draft (`draft`) or a
 * Version's ID. It is fetched again when the Versions or the saved Draft's revision (`draft`) change.
 */
export function useInstructionsDiff(organisationId: string, projectId: string, sides: { from: string; to: string; draft: number | undefined }) {
  return useQuery({
    queryKey: [...versionsKey(organisationId, projectId), "diff", sides],
    queryFn: async (): Promise<InstructionsDiff> => {
      const { data, error, response } = await api.GET("/api/organisations/{organisation_id}/projects/{project_id}/instructions/diff", {
        params: { path: { organisation_id: organisationId, project_id: projectId }, query: { from: sides.from, to: sides.to } },
      });
      if (!data) throw failed(response, error);
      return data;
    },
  });
}
