import type { Schemas } from "@studio/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api";

export type ThemeOverride = Schemas["ThemeOverrideOut"];
export type ColourValue = Schemas["ColourToken"];

type Path = { organisation_id: string; project_id: string; agent_id: string };

const PATH = "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/theme-override";
const AVATAR = `${PATH}/avatar` as const;

const overrideKey = (path: Path) => ["theme-override", path.organisation_id, path.agent_id] as const;

/** Why a change to the Theme override failed: the API's reason, or a generic one. */
export class BrandingError extends Error {}

const SAVE_FAILED = "Something went wrong. Try again.";
const UPLOAD_FAILED = "The upload failed. Try again.";
const REMOVE_FAILED = "The avatar couldn't be removed. Try again.";

function reason(error: unknown, fallback: string): string {
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === "string") return detail;
  const first = Array.isArray(detail) ? (detail[0] as { msg?: unknown } | undefined) : undefined;
  return typeof first?.msg === "string" ? first.msg : fallback;
}

/** The Agent's Theme override: the colour tokens it replaces and its own avatar. */
export function useThemeOverride(path: Path) {
  return useQuery({
    queryKey: overrideKey(path),
    queryFn: async (): Promise<ThemeOverride> => {
      const { data } = await api.GET(PATH, { params: { path } });
      if (!data) throw new BrandingError();
      return data;
    },
  });
}

/** Replaces the colours the Agent overrides; the widget's next page load uses them. */
export function useSaveOverrideColours(path: Path) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (colours: Record<string, ColourValue>): Promise<ThemeOverride> => {
      const { data, error } = await api.PUT(PATH, { params: { path }, body: { colours } });
      if (!data) throw new BrandingError(reason(error, SAVE_FAILED));
      return data;
    },
    onSuccess: (saved) => {
      queryClient.setQueryData(overrideKey(path), saved);
    },
  });
}

export type AvatarAction =
  | { phase: "idle" }
  | { phase: "uploading" }
  | { phase: "removing" }
  | { phase: "uploaded" }
  | { phase: "removed" }
  | { phase: "failed"; message: string };

/**
 * Uploads, replaces and removes the Agent's own avatar, as the Theme's images are: presign,
 * PUT straight to storage, confirm. It applies to the widget at once.
 */
export function useAgentAvatar(path: Path) {
  const queryClient = useQueryClient();
  const [action, setAction] = useState<AvatarAction>({ phase: "idle" });
  const applied = (saved: ThemeOverride) => {
    queryClient.setQueryData(overrideKey(path), saved);
  };

  async function uploaded(file: File): Promise<AvatarAction> {
    const started = await api.POST(`${AVATAR}/uploads`, {
      params: { path },
      body: { filename: file.name, size_bytes: file.size },
    });
    if (!started.data) return { phase: "failed", message: reason(started.error, UPLOAD_FAILED) };
    const stored = await fetch(started.data.url, {
      method: "PUT",
      headers: { "Content-Type": started.data.content_type },
      body: file,
    });
    if (!stored.ok) return { phase: "failed", message: UPLOAD_FAILED };
    const confirmed = await api.PUT(AVATAR, { params: { path }, body: { upload_id: started.data.upload_id } });
    if (!confirmed.data) return { phase: "failed", message: reason(confirmed.error, UPLOAD_FAILED) };
    applied(confirmed.data);
    return { phase: "uploaded" };
  }

  async function upload(file: File) {
    setAction({ phase: "uploading" });
    try {
      setAction(await uploaded(file));
    } catch {
      setAction({ phase: "failed", message: UPLOAD_FAILED });
    }
  }

  async function remove() {
    setAction({ phase: "removing" });
    try {
      const { data } = await api.DELETE(AVATAR, { params: { path } });
      if (!data) {
        setAction({ phase: "failed", message: REMOVE_FAILED });
        return;
      }
      applied(data);
      setAction({ phase: "removed" });
    } catch {
      setAction({ phase: "failed", message: REMOVE_FAILED });
    }
  }

  return { action, upload, remove };
}
