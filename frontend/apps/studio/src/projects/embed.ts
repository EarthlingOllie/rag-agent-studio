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

/** The API's reason for a refusal: its first validation message, or the detail of a refusal by the
 * voice layer or a client error (4xx); anything else is a generic reason. */
function reason(error: unknown, status: number): string {
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  const first = Array.isArray(detail) ? (detail[0] as { msg?: unknown } | undefined) : undefined;
  if (typeof first?.msg === "string") return first.msg;
  const explained = status === 502 || status < 500;
  return explained && typeof detail === "string" ? detail : "Something went wrong. Try again.";
}

type Path = { organisation_id: string; project_id: string; agent_id: string };

/** An Agent's Allowed Origins, unavailable text, rate limits, Token Budget, Call settings and Call
 * limits: not part of its Draft or Versions. */
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

/** Today's (UTC) Call minutes against the Agent's Call minutes budget. */
export type CallMinutes = Schemas["CallMinutesOut"];

const minutesKey = (path: Path) => ["call-minutes", path.organisation_id, path.agent_id] as const;

/** Why today's Call minutes couldn't be loaded. */
export class CallMinutesError extends Error {}

/** Today's Call minutes against the Call minutes budget, for the Call minutes meter. */
export function useCallMinutes(path: Path) {
  return useQuery({
    queryKey: minutesKey(path),
    queryFn: async (): Promise<CallMinutes> => {
      const { data } = await api.GET(
        "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/call-minutes",
        { params: { path } },
      );
      if (!data) throw new CallMinutesError();
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
      const { data, error, response } = await api.PATCH(PATH, { params: { path }, body: change });
      if (!data) throw new OperationalSettingsError(reason(error, response.status));
      return data;
    },
    onSuccess: (settings) => {
      queryClient.setQueryData(settingsKey(path), settings);
      // The meters measure against the budgets.
      void queryClient.invalidateQueries({ queryKey: usageKey(path) });
      void queryClient.invalidateQueries({ queryKey: minutesKey(path) });
      // Saving the Call settings can clear the Agent's Calls failing alert.
      void queryClient.invalidateQueries({ queryKey: ["agents", path.organisation_id, path.project_id] });
    },
  });
}

/** A voice of a voice-capable credential's ElevenLabs account, with a sample to listen to. */
export type Voice = Schemas["VoiceOut"];

/** Why a credential's voices couldn't be listed. */
export class VoicesError extends Error {}

/** The voices a voice-capable credential offers, for the Call settings' voice picker; nothing is
 * asked until a credential is chosen. */
export function useVoices(organisationId: string, credentialId: string | null) {
  return useQuery({
    queryKey: ["voices", organisationId, credentialId] as const,
    enabled: credentialId !== null,
    retry: false,
    queryFn: async (): Promise<Voice[]> => {
      const { data, error, response } = await api.GET("/api/organisations/{organisation_id}/credentials/{credential_id}/voices", {
        // Only asked once a credential is chosen.
        params: { path: { organisation_id: organisationId, credential_id: credentialId as string } },
      });
      if (!data) throw new VoicesError(reason(error, response.status));
      return data;
    },
  });
}
