import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";
import type { Schemas } from "@studio/api-client";

/** The snippet's Launcher choice: none (the Theme's), a bubble, or inline in a container. */
export type SnippetLayout = { launcher: "theme" } | { launcher: "bubble" } | { launcher: "inline"; target: string };

function attribute(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

/** The Embed Snippet a web team pastes into its pages; it loads the widget from this origin. */
export function embedSnippet(
  publicId: string,
  origin = window.location.origin,
  layout: SnippetLayout = { launcher: "theme" },
): string {
  let attributes = "";
  if (layout.launcher === "bubble") attributes = ' data-launcher="bubble"';
  if (layout.launcher === "inline") {
    attributes = ' data-launcher="inline"';
    if (layout.target.trim()) attributes += ` data-target="${attribute(layout.target.trim())}"`;
  }
  return `<script src="${origin}/embed.js" data-agent="${publicId}"${attributes} async></script>`;
}

/** Why the Operational Settings couldn't be loaded or saved: the API's reason, or a generic one. */
export class OperationalSettingsError extends Error {}

type Path = { organisation_id: string; project_id: string; agent_id: string };

/** An Agent's Allowed Origins, unavailable text, rate limits and Token Budget: not part of its
 * Draft or Versions. */
export type OperationalSettings = Schemas["OperationalSettingsOut"];

const PATH =
  "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/operational-settings";

const settingsKey = (path: Path) =>
  ["operational-settings", path.organisation_id, path.agent_id] as const;

/** Today's (UTC) Visitor usage against the Agent's Token Budget. */
export type TokenUsage = Schemas["TokenUsageOut"];

const usageKey = (path: Path) => ["token-usage", path.organisation_id, path.agent_id] as const;

/** Why today's usage couldn't be loaded. */
export class TokenUsageError extends Error {}

/** Today's usage against the Token Budget, for the budget meter. */
export function useTokenUsage(path: Path) {
  return useQuery({
    queryKey: usageKey(path),
    queryFn: async (): Promise<TokenUsage> => {
      const { data } = await api.GET(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/token-usage",
        { params: { path } },
      );
      if (!data) throw new TokenUsageError();
      return data;
    },
  });
}

/** The Agent's Operational Settings. */
export function useOperationalSettings(path: Path) {
  return useQuery({
    queryKey: settingsKey(path),
    queryFn: async (): Promise<OperationalSettings> => {
      const { data } = await api.GET(PATH, { params: { path } });
      if (!data) throw new OperationalSettingsError();
      return data;
    },
  });
}

/** Changes the settings given, leaving the others; the widget's next request uses them. */
export function useChangeOperationalSettings(path: Path) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (
      change: Schemas["OperationalSettingsChange"],
    ): Promise<OperationalSettings> => {
      const { data, error } = await api.PATCH(PATH, { params: { path }, body: change });
      if (!data) {
        const detail = (error as { detail?: unknown }).detail;
        const first = Array.isArray(detail) ? (detail[0] as { msg?: unknown } | undefined) : undefined;
        throw new OperationalSettingsError(
          typeof first?.msg === "string" ? first.msg : "Something went wrong. Try again.",
        );
      }
      return data;
    },
    onSuccess: (settings) => {
      queryClient.setQueryData(settingsKey(path), settings);
      // The meter measures against the budget.
      void queryClient.invalidateQueries({ queryKey: usageKey(path) });
    },
  });
}
