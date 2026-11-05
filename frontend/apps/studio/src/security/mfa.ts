import type { Schemas } from "@studio/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";
import { AuthRequestError } from "../auth/session";

export type MfaStatus = Schemas["MfaStatusResponse"];
export type Enrolment = Schemas["EnrolmentResponse"];

const MFA_QUERY_KEY = ["mfa"] as const;

/** Unwraps a response, turning any non-2xx answer into an `AuthRequestError`. */
function body<Data>({ data, response }: { data?: Data; response: Response }): Data {
  if (data === undefined) throw new AuthRequestError(response.status);
  return data;
}

export function useMfaStatus() {
  return useQuery({
    queryKey: MFA_QUERY_KEY,
    queryFn: async () => body(await api.GET("/api/auth/mfa")),
  });
}

/** Mutations that change MFA refresh the status once they succeed. */
function useMfaMutation<Variables, Result>(request: (variables: Variables) => Promise<Result>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: request,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: MFA_QUERY_KEY }),
  });
}

export function useStartEnrolment() {
  return useMutation({ mutationFn: async () => body(await api.POST("/api/auth/mfa/enrolment")) });
}

export function useConfirmEnrolment() {
  return useMfaMutation(async (code: string) =>
    body(await api.POST("/api/auth/mfa/enrolment/confirm", { body: { code } })),
  );
}

export function useReplaceRecoveryCodes() {
  return useMfaMutation(async (code: string) =>
    body(await api.POST("/api/auth/mfa/recovery-codes", { body: { code } })),
  );
}

export function useDisableMfa() {
  return useMfaMutation(async (details: { password: string; code: string }) => {
    const { response } = await api.POST("/api/auth/mfa/disable", { body: details });
    if (!response.ok) throw new AuthRequestError(response.status);
  });
}
