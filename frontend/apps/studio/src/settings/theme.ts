import type { Schemas } from "@studio/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";

export type SavedTheme = Schemas["ThemeOut"];
export type ThemeSettings = Schemas["ThemeSettings"];
export type ThemeFont = Schemas["FontOut"];

export const themeKey = (organisationId: string) => ["theme", organisationId] as const;

export function useTheme(organisationId: string) {
  return useQuery({
    queryKey: themeKey(organisationId),
    queryFn: async (): Promise<SavedTheme> => {
      const { data } = await api.GET("/api/organisations/{organisation_id}/theme", {
        params: { path: { organisation_id: organisationId } },
      });
      if (!data) throw new Error("The Theme could not be loaded");
      return data;
    },
  });
}

export function useThemeFonts() {
  return useQuery({
    queryKey: ["theme-fonts"],
    queryFn: async (): Promise<ThemeFont[]> => {
      const { data } = await api.GET("/api/themes/fonts");
      if (!data) throw new Error("The fonts could not be loaded");
      return data;
    },
    staleTime: Infinity,
  });
}

export function useSaveTheme(organisationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (theme: ThemeSettings): Promise<SavedTheme> => {
      const { data } = await api.PUT("/api/organisations/{organisation_id}/theme", {
        params: { path: { organisation_id: organisationId } },
        body: theme,
      });
      if (!data) throw new Error("The Theme could not be saved");
      return data;
    },
    onSuccess: (saved) => {
      queryClient.setQueryData(themeKey(organisationId), saved);
    },
  });
}
