import { randomUUID } from "node:crypto";

import type { APIRequestContext, Page } from "@playwright/test";

/**
 * Signed-in page helpers. They drive the auth API directly, so a test about, say, the Members screen
 * doesn't sign up through the UI first. The routes and body fields are the contract ticket 01-04
 * implements; change them here if that ticket settles on different ones.
 */
export const AUTH_ROUTES = {
  signUp: "/api/auth/sign-up",
  signIn: "/api/auth/sign-in",
} as const;

/** What a person types to sign up: their name, email, password and a new Organisation's name. */
export interface MemberCredentials {
  name: string;
  email: string;
  password: string;
  organisationName: string;
}

/** A Member nobody has signed up yet. Every call gives a unique email so tests never collide. */
export function newMember(overrides: Partial<MemberCredentials> = {}): MemberCredentials {
  const id = randomUUID().slice(0, 8);
  return {
    name: `E2E Member ${id}`,
    email: `e2e-${id}-${randomUUID()}@example.test`,
    password: `correct horse battery staple ${id}`,
    organisationName: `E2E Organisation ${id}`,
    ...overrides,
  };
}

async function post(request: APIRequestContext, route: string, data: Record<string, string>): Promise<void> {
  const response = await request.post(route, { data });
  if (!response.ok()) {
    throw new Error(`POST ${route} answered ${String(response.status())}: ${await response.text()}`);
  }
}

/** Signs a new Member up, which makes them the Owner of a new Organisation. */
export async function signUp(request: APIRequestContext, member: MemberCredentials): Promise<void> {
  await post(request, AUTH_ROUTES.signUp, {
    name: member.name,
    email: member.email,
    password: member.password,
    organisation_name: member.organisationName,
  });
}

/** Signs in; the session cookie lands in whichever browser context owns `request`. */
export async function signIn(request: APIRequestContext, member: Pick<MemberCredentials, "email" | "password">): Promise<void> {
  await post(request, AUTH_ROUTES.signIn, { email: member.email, password: member.password });
}

/** Signs an existing Member into `page`; its context then carries the session cookie. */
export async function signInAs(page: Page, member: Pick<MemberCredentials, "email" | "password">): Promise<void> {
  await signIn(page.request, member);
}
