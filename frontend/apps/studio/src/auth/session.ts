import type { Schemas } from "@studio/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";

export type Session = Schemas["SessionResponse"];
export type SignUpDetails = Schemas["SignUpRequest"];
export type SignInDetails = Schemas["SignInRequest"];

export const ME_QUERY_KEY = ["me"] as const;

/** A failed auth request; `status` is the HTTP status the API answered with. */
export class AuthRequestError extends Error {
  constructor(readonly status: number) {
    super(`The API answered ${String(status)}`);
  }
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

function useStartSession<Details>(request: (details: Details) => Promise<{ data?: Session; response: Response }>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (details: Details) => {
      const { data, response } = await request(details);
      if (!data) throw new AuthRequestError(response.status);
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

export function useSignIn() {
  return useStartSession((body: SignInDetails) => api.POST("/api/auth/sign-in", { body }));
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
