import type { Schemas } from "@studio/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";

export type Session = Schemas["SessionResponse"];
export type SignUpDetails = Schemas["SignUpRequest"];
export type SignInDetails = Schemas["SignInRequest"];

export const ME_QUERY_KEY = ["me"] as const;

export type Throttled = Schemas["ThrottledResponse"];

/** A failed auth request; `status` is the HTTP status the API answered with, `body` its JSON. */
export class AuthRequestError extends Error {
  constructor(
    readonly status: number,
    readonly body?: unknown,
  ) {
    super(`The API answered ${String(status)}`);
  }
}

/** The details of a sign-in the API delayed or locked out, or undefined for any other error. */
export function throttledDetails(error: Error): Throttled | undefined {
  if (!(error instanceof AuthRequestError) || error.status !== 429) return undefined;
  const body = Object(error.body) as Partial<Throttled>; // no body reads as {}
  return typeof body.retry_after_seconds === "number" ? (body as Throttled) : undefined;
}

/** The signed-in Member and their Organisations, or null when nobody is signed in. */
export function useMe() {
  return useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: async (): Promise<Session | null> => {
      const { data, response } = await api.GET("/api/auth/me");
      if (data) return data;
      if (response.status === 401) return null;
      throw new AuthRequestError(response.status);
    },
  });
}

function useStartSession<Details>(
  request: (details: Details) => Promise<{ data?: Session; error?: unknown; response: Response }>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (details: Details) => {
      const { data, error, response } = await request(details);
      if (!data) throw new AuthRequestError(response.status, error);
      return data;
    },
    onSuccess: (session) => {
      queryClient.setQueryData(ME_QUERY_KEY, session);
    },
  });
}

export function useSignUp() {
  return useStartSession((body: SignUpDetails) => api.POST("/api/auth/sign-up", { body }));
}

/** What a correct password leads to: a session, or (for a Member with MFA) a code challenge. */
export type SignInOutcome = { mfaRequired: false; session: Session } | { mfaRequired: true };

export function useSignIn() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: SignInDetails): Promise<SignInOutcome> => {
      const { data, error, response } = await api.POST("/api/auth/sign-in", { body });
      if (data === undefined) throw new AuthRequestError(response.status, error);
      if ("mfa_required" in data) return { mfaRequired: true };
      return { mfaRequired: false, session: data };
    },
    onSuccess: (outcome) => {
      if (!outcome.mfaRequired) queryClient.setQueryData(ME_QUERY_KEY, outcome.session);
    },
  });
}

/** Finishes an MFA-pending sign-in with an authenticator or recovery code. */
export function useVerifyMfa() {
  return useStartSession((code: string) => api.POST("/api/auth/mfa/verify", { body: { code } }));
}

export function useSignOut() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { response } = await api.POST("/api/auth/sign-out");
      if (!response.ok) throw new AuthRequestError(response.status);
    },
    onSuccess: () => {
      queryClient.setQueryData(ME_QUERY_KEY, null);
    },
  });
}

export type PasswordResetRequest = Schemas["PasswordResetRequest"];
export type CompletePasswordReset = Schemas["CompletePasswordResetRequest"];
export type ChangePassword = Schemas["ChangePasswordRequest"];

export function useRequestPasswordReset() {
  return useMutation({
    mutationFn: async (body: PasswordResetRequest) => {
      const { response } = await api.POST("/api/auth/password-reset", { body });
      if (!response.ok) throw new AuthRequestError(response.status);
    },
  });
}

export function useCompletePasswordReset() {
  return useMutation({
    mutationFn: async (body: CompletePasswordReset) => {
      const { response } = await api.POST("/api/auth/password-reset/complete", { body });
      if (!response.ok) throw new AuthRequestError(response.status);
    },
  });
}

export function useUpdateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["UpdateProfileRequest"]) => {
      const { data, response } = await api.PATCH("/api/auth/me", { body });
      if (!data) throw new AuthRequestError(response.status);
      return data;
    },
    onSuccess: (session) => {
      queryClient.setQueryData(ME_QUERY_KEY, session);
    },
  });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: async (body: ChangePassword) => {
      const { response } = await api.POST("/api/auth/me/password", { body });
      if (!response.ok) throw new AuthRequestError(response.status);
    },
  });
}

/** Makes one of the Member's Organisations the active one; the API remembers it across sign-ins. */
export function useSwitchOrganisation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (organisationId: string) => {
      const { data, response } = await api.PUT("/api/auth/me/active-organisation", {
        body: { organisation_id: organisationId },
      });
      if (!data) throw new AuthRequestError(response.status);
      return data;
    },
    onSuccess: (session) => {
      queryClient.setQueryData(ME_QUERY_KEY, session);
    },
  });
}
