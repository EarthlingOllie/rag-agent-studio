import type { Schemas } from "@studio/api-client";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api";
import { type SavedTheme, themeKey } from "./theme";

export type ThemeImage = Schemas["ThemeImageOut"];
export type ThemeImageKind = Schemas["ThemeImageKind"];

export type ImageAction =
  | { phase: "idle" }
  | { phase: "uploading" }
  | { phase: "removing" }
  | { phase: "uploaded" }
  | { phase: "removed" }
  | { phase: "failed"; message: string };

const UPLOAD_FAILED = "The upload failed. Try again.";
const REMOVE_FAILED = "The image couldn't be removed. Try again.";

function reason(error: unknown, fallback: string): string {
  const detail = (error as { detail?: unknown }).detail;
  return typeof detail === "string" ? detail : fallback;
}

/**
 * Uploads, replaces and removes one of the Theme's images. An upload asks the API for a
 * presigned URL (it checks the type and size first), PUTs the file straight to storage, then
 * confirms; the API answers with the Theme, which replaces the cached one. Images apply at once,
 * apart from the Theme's other settings and their Save button.
 */
export function useThemeImage(organisationId: string, kind: ThemeImageKind) {
  const queryClient = useQueryClient();
  const [action, setAction] = useState<ImageAction>({ phase: "idle" });
  const path = { organisation_id: organisationId, kind };

  const applied = (theme: SavedTheme) => {
    queryClient.setQueryData(themeKey(organisationId), theme);
  };

  async function upload(file: File) {
    setAction({ phase: "uploading" });
    const started = await api.POST("/api/organisations/{organisation_id}/theme/images/{kind}/uploads", {
      params: { path },
      body: { filename: file.name, size_bytes: file.size },
    });
    if (!started.data) {
      setAction({ phase: "failed", message: reason(started.error, UPLOAD_FAILED) });
      return;
    }
    const stored = await fetch(started.data.url, {
      method: "PUT",
      headers: { "Content-Type": started.data.content_type },
      body: file,
    });
    if (!stored.ok) {
      setAction({ phase: "failed", message: UPLOAD_FAILED });
      return;
    }
    const confirmed = await api.PUT("/api/organisations/{organisation_id}/theme/images/{kind}", {
      params: { path },
      body: { upload_id: started.data.upload_id },
    });
    if (!confirmed.data) {
      setAction({ phase: "failed", message: reason(confirmed.error, UPLOAD_FAILED) });
      return;
    }
    applied(confirmed.data);
    setAction({ phase: "uploaded" });
  }

  async function remove() {
    setAction({ phase: "removing" });
    const { data } = await api.DELETE("/api/organisations/{organisation_id}/theme/images/{kind}", { params: { path } });
    if (!data) {
      setAction({ phase: "failed", message: REMOVE_FAILED });
      return;
    }
    applied(data);
    setAction({ phase: "removed" });
  }

  return { action, upload, remove };
}
