import type { Schemas } from "@studio/api-client";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api } from "../api";
import type { Trace } from "./agents";
import { ProjectRequestError } from "./projects";

export type ConversationPage = Schemas["ConversationPageOut"];
export type ConversationSummary = ConversationPage["items"][number];
export type ConversationDetail = Schemas["ConversationDetailOut"];
export type ConversationMessage = ConversationDetail["messages"][number];

export const PAGE_SIZE = 25;

/**
 * The Conversations list's filters, kept in the tab's URL so they survive opening a
 * Conversation: an Agent, one of its Versions, `YYYY-MM-DD` UTC days (both inclusive), which
 * Conversations to show (Visitors' or the Playground's; both when left out), their Message
 * Feedback (a reply with a thumbs up or down, any feedback, or none), their Conversation Rating
 * (one score, rated, or not rated), their Guardrail outcomes (a reply whose Guardrail took one
 * action, any Guardrail outcome, or none) and the page.
 */
export interface ConversationFilters {
  agent?: string;
  version?: string;
  from?: string;
  to?: string;
  show?: "visitors" | "playground";
  feedback?: FeedbackFilter;
  rating?: RatingFilter;
  guardrail?: GuardrailFilter;
  page?: number;
}

export type GuardrailFilter = Schemas["GuardrailFilter"];
const GUARDRAIL_FILTERS: readonly unknown[] = [
  "blocked",
  "flagged",
  "logged",
  "replaced",
  "allowed",
  "any",
  "none",
] satisfies GuardrailFilter[];

export type FeedbackFilter = "up" | "down" | "any" | "none";
const FEEDBACK_FILTERS: readonly unknown[] = ["up", "down", "any", "none"] satisfies FeedbackFilter[];

/** A score is kept as a number, so the URL reads `?rating=4` (the router quotes a numeric string). */
export type RatingFilter = 1 | 2 | 3 | 4 | 5 | "any" | "none";
const RATING_FILTERS: readonly unknown[] = [1, 2, 3, 4, 5, "any", "none"] satisfies RatingFilter[];

/** The filters in a URL's search (or any record), leaving out anything that isn't one, an empty
 * value, and the first page. */
export function conversationFilters(search: Record<string, unknown>): ConversationFilters {
  const filters: ConversationFilters = {};
  for (const key of ["agent", "version", "from", "to"] as const) {
    const value = search[key];
    if (typeof value === "string" && value !== "") filters[key] = value;
  }
  if (search.show === "visitors" || search.show === "playground") filters.show = search.show;
  if (FEEDBACK_FILTERS.includes(search.feedback)) filters.feedback = search.feedback as FeedbackFilter;
  // A score comes as a number from the URL, or as a string from the filter's select.
  const rating = typeof search.rating === "string" && /^[1-5]$/.test(search.rating) ? Number(search.rating) : search.rating;
  if (RATING_FILTERS.includes(rating)) filters.rating = rating as RatingFilter;
  if (GUARDRAIL_FILTERS.includes(search.guardrail)) filters.guardrail = search.guardrail as GuardrailFilter;
  const page = Number(search.page);
  if (Number.isInteger(page) && page > 1) filters.page = page;
  return filters;
}

const DAY_MS = 24 * 60 * 60 * 1000;

function startOfUtcDay(day: string, plusDays = 0): string {
  return new Date(Date.parse(`${day}T00:00:00Z`) + plusDays * DAY_MS).toISOString();
}

/** The API query for these filters; a filter left out is left out. */
function listQuery(filters: ConversationFilters) {
  return {
    ...(filters.agent && { agent_id: filters.agent }),
    ...(filters.version && { version_id: filters.version }),
    ...(filters.from && { start: startOfUtcDay(filters.from) }),
    // The To day is inclusive here; the API's end is exclusive.
    ...(filters.to && { end: startOfUtcDay(filters.to, 1) }),
    ...(filters.show && { playground: filters.show === "playground" }),
    ...(filters.feedback && { feedback: filters.feedback }),
    ...(filters.rating && { rating: String(filters.rating) as Schemas["RatingFilter"] }),
    ...(filters.guardrail && { guardrail: filters.guardrail }),
  };
}

function failed(response: Response): ProjectRequestError {
  return new ProjectRequestError(response.status);
}

export function useConversations(organisationId: string, projectId: string, filters: ConversationFilters) {
  const page = filters.page ?? 1;
  return useQuery({
    queryKey: ["conversations", organisationId, projectId, filters],
    placeholderData: keepPreviousData,
    queryFn: async (): Promise<ConversationPage> => {
      const { data, response } = await api.GET("/api/organisations/{organisation_id}/projects/{project_id}/conversations", {
        params: {
          path: { organisation_id: organisationId, project_id: projectId },
          query: { ...listQuery(filters), page, page_size: PAGE_SIZE },
        },
      });
      if (!data) throw failed(response);
      return data;
    },
  });
}

export type ConversationPath = { organisation_id: string; project_id: string; conversation_id: string };

export function useConversation(path: ConversationPath) {
  return useQuery({
    queryKey: ["conversation", path.organisation_id, path.conversation_id],
    queryFn: async (): Promise<ConversationDetail> => {
      const { data, response } = await api.GET(
        "/api/organisations/{organisation_id}/projects/{project_id}/conversations/{conversation_id}",
        { params: { path } },
      );
      if (!data) throw failed(response);
      return data;
    },
  });
}

export function useConversationTrace(path: ConversationPath & { message_id: string }) {
  return useQuery({
    queryKey: ["conversation-trace", path.organisation_id, path.message_id],
    queryFn: async (): Promise<Trace> => {
      const { data, response } = await api.GET(
        "/api/organisations/{organisation_id}/projects/{project_id}/conversations/{conversation_id}/messages/{message_id}/trace",
        { params: { path } },
      );
      if (!data) throw failed(response);
      return data;
    },
    retry: false,
  });
}
