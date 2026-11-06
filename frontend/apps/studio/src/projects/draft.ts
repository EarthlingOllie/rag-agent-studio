import type { Schemas } from "@studio/api-client";
import { useQuery } from "@tanstack/react-query";

import { api } from "../api";
import type { Capability } from "../settings/credentials";
import { ProjectRequestError } from "./projects";

export type Draft = Schemas["AgentConfig-Output"];
export type ModelChoice = Schemas["ModelChoice"];

/** One setting the API refused: where it is (its path in the Draft, dot-separated) and why. */
export type FieldError = { field: string; message: string };

/** A refused Draft save. A 422 carries the refused settings; other refusals the API's reason. */
export class DraftRequestError extends ProjectRequestError {
  constructor(
    status: number,
    detail: string | undefined,
    readonly fields: FieldError[],
  ) {
    super(status, detail);
  }
}

type ValidationDetail = { loc: (string | number)[]; msg: string }[];

export function draftFailed(response: Response, error: unknown): DraftRequestError {
  const detail = (error as { detail?: unknown }).detail;
  if (Array.isArray(detail)) {
    // Locations start with "body", the request part the setting was in.
    const fields = (detail as ValidationDetail).map(({ loc, msg }) => ({ field: loc.slice(1).join("."), message: msg }));
    return new DraftRequestError(response.status, undefined, fields);
  }
  return new DraftRequestError(response.status, typeof detail === "string" ? detail : undefined, []);
}

/** The errors for one setting: those located at it or inside it. */
export function errorsFor(errors: FieldError[], field: string): string[] {
  return errors.filter((error) => error.field === field || error.field.startsWith(`${field}.`)).map((error) => error.message);
}

/** The models a credential offers for a capability. */
export function useCredentialModels(organisationId: string, credentialId: string, capability: Capability) {
  return useQuery({
    queryKey: ["credential-models", organisationId, credentialId, capability],
    enabled: credentialId !== "",
    queryFn: async (): Promise<Schemas["ModelOut"][]> => {
      const { data } = await api.GET("/api/organisations/{organisation_id}/credentials/{credential_id}/models/{capability}", {
        params: { path: { organisation_id: organisationId, credential_id: credentialId, capability } },
      });
      // A credential whose models can't be listed offers none to choose from.
      return data ?? [];
    },
  });
}
