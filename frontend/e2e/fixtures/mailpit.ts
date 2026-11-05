import type { APIRequestContext } from "@playwright/test";

import { MAILPIT_URL } from "./env";

interface MailpitSummary {
  ID: string;
}

interface MailpitMessage {
  Subject: string;
  Text: string;
}

/**
 * The newest email Mailpit received for `address`, read through Mailpit's API. Email is sent after
 * the API answers, so this polls until one arrives.
 */
export async function latestEmailTo(
  request: APIRequestContext,
  address: string,
  { timeoutMs = 15_000, intervalMs = 250 } = {},
): Promise<MailpitMessage> {
  const deadline = Date.now() + timeoutMs;
  const search = new URL("/api/v1/search", MAILPIT_URL);
  search.searchParams.set("query", `to:"${address}"`);
  for (;;) {
    const response = await request.get(search.toString());
    if (!response.ok()) throw new Error(`Mailpit search answered ${String(response.status())}`);
    const { messages } = (await response.json()) as { messages: MailpitSummary[] };
    const newest = messages[0];
    if (newest !== undefined) {
      const message = await request.get(new URL(`/api/v1/message/${newest.ID}`, MAILPIT_URL).toString());
      return (await message.json()) as MailpitMessage;
    }
    if (Date.now() > deadline) throw new Error(`No email reached Mailpit for ${address}`);
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

/** The first link in `text` to `path` on any host, as a path and query to open on the Studio under test. */
export function linkPath(text: string, path: string): string {
  const match = new RegExp(`https?://\\S+?(${path}\\?\\S+)`).exec(text);
  if (match?.[1] === undefined) throw new Error(`No ${path} link in:\n${text}`);
  return match[1];
}
