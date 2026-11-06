import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";

/** The Embed Snippet a web team pastes into its pages; it loads the widget from this origin. */
export function embedSnippet(publicId: string, origin = window.location.origin): string {
  return `<script src="${origin}/embed.js" data-agent="${publicId}" async></script>`;
}

/** Why saving the Allowed Origins failed: the API's reason for a bad origin, or a generic one. */
export class AllowedOriginsError extends Error {}

type Path = { organisation_id: string; project_id: string; agent_id: string };

const PATH =
  "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/allowed-origins";

const originsKey = (path: Path) => ["allowed-origins", path.organisation_id, path.agent_id] as const;

/** The sites whose pages may show the Agent's widget. */
export function useAllowedOrigins(path: Path) {
  return useQuery({
    queryKey: originsKey(path),
    queryFn: async (): Promise<string[]> => {
      const { data } = await api.GET(PATH, { params: { path } });
      if (!data) throw new AllowedOriginsError();
      return data.origins;
    },
  });
}

/** Replaces the Allowed Origins; the widget's next page load uses them. */
export function useSaveAllowedOrigins(path: Path) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (origins: string[]): Promise<string[]> => {
      const { data, error } = await api.PUT(PATH, { params: { path }, body: { origins } });
      if (!data) {
        const detail = (error as { detail?: unknown }).detail;
        const first = Array.isArray(detail) ? (detail[0] as { msg?: unknown } | undefined) : undefined;
        throw new AllowedOriginsError(
          typeof first?.msg === "string" ? first.msg : "Something went wrong. Try again.",
        );
      }
      return data.origins;
    },
    onSuccess: (origins) => {
      queryClient.setQueryData(originsKey(path), origins);
    },
  });
}
