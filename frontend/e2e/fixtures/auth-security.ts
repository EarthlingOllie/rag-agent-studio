import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import { promisify } from "node:util";

import type { APIRequestContext } from "@playwright/test";

import { MAILPIT_URL } from "./env";

/**
 * Helpers for the auth-hardening specs (`tests/auth-security.spec.ts`).
 *
 * Sign-in throttling counts failures per account and per client IP. Every request the browser
 * sends reaches the API through the Studio's proxy, so the whole suite shares one IP counter
 * there. Specs that need many failed sign-ins send them straight to the API instead
 * (`API_URL`), whose peer is the host, so the Studio's shared IP counter is left alone.
 */
export const API_URL = process.env.E2E_API_URL ?? "http://localhost:8000";

/** The stack's Postgres container, for moving a link's expiry into the past. */
const POSTGRES_CONTAINER = process.env.E2E_POSTGRES_CONTAINER ?? "rag-agent-studio-postgres-1";

const run = promisify(execFile);

/** SHA-256 of a link's token, as the API stores it (only the hash is kept). */
function tokenHash(token: string): string {
  return createHash("sha256").update(token).digest("hex");
}

async function psql(sql: string): Promise<string> {
  const { stdout } = await run("docker", [
    "exec",
    POSTGRES_CONTAINER,
    "psql",
    "-U",
    "studio",
    "-d",
    "studio",
    "-v",
    "ON_ERROR_STOP=1",
    "-tAc",
    sql,
  ]);
  return stdout.trim();
}

/**
 * Lets the time a link is valid for run out, as if the clock had moved past its expiry. The stack
 * has no controllable clock, so the stored expiry of the one link with this token is set to a
 * minute ago instead. Throws unless exactly one link matched.
 */
export async function expireLink(kind: "password_reset_tokens" | "invites", token: string): Promise<void> {
  const outcome = await psql(`UPDATE ${kind} SET expires_at = now() - interval '1 minute' WHERE token_hash = '${tokenHash(token)}'`);
  if (outcome !== "UPDATE 1") throw new Error(`Expected one ${kind} row with that token, got: ${outcome}`);
}

/** The token in a link's query string. */
export function linkToken(link: string): string {
  const token = new URL(link, "http://studio.invalid").searchParams.get("token");
  if (!token) throw new Error(`No token in ${link}`);
  return token;
}

/** How many emails Mailpit holds for `address`, without waiting for one to arrive. */
export async function emailCount(request: APIRequestContext, address: string): Promise<number> {
  const search = new URL("/api/v1/search", MAILPIT_URL);
  search.searchParams.set("query", `to:"${address}"`);
  const response = await request.get(search.toString());
  if (!response.ok()) throw new Error(`Mailpit search answered ${String(response.status())}`);
  return ((await response.json()) as { messages: unknown[] }).messages.length;
}
