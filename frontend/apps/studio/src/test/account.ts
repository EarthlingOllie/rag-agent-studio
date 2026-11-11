import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import { adaSession, type Session } from "./auth";
import { notSignedIn, server } from "./server";

/** The tokens the fake API accepts for a password reset. Each works once. */
export const VALID_RESET_TOKEN = "a-valid-reset-token";

const invalidLink: Schemas["ErrorResponse"] = { detail: "This reset link is invalid or has expired." };
const wrongCurrentPassword: Schemas["ErrorResponse"] = { detail: "Current password is incorrect" };

/**
 * A stateful stand-in for the account API: password reset, Profile edits and password changes.
 * `currentPassword` is the password the fake Member has; changing it updates it.
 */
export function fakeAccountApi(options: { signedInAs?: Session; currentPassword?: string } = {}) {
  let current: Session | undefined = options.signedInAs;
  let password = options.currentPassword ?? "correct horse battery";
  const unusedTokens = new Set([VALID_RESET_TOKEN]);
  const requests: { route: string; body: unknown }[] = [];

  server.use(
    http.get("*/api/auth/me", () =>
      current ? HttpResponse.json(current) : HttpResponse.json(notSignedIn, { status: 401 }),
    ),
    http.post("*/api/auth/password-reset", async ({ request }) => {
      requests.push({ route: "password-reset", body: await request.json() });
      return HttpResponse.json({ detail: "If that email is registered, a reset link is on its way." }, { status: 202 });
    }),
    http.post("*/api/auth/password-reset/complete", async ({ request }) => {
      const body = (await request.json()) as Schemas["CompletePasswordResetRequest"];
      requests.push({ route: "password-reset/complete", body });
      if (!unusedTokens.delete(body.token)) return HttpResponse.json(invalidLink, { status: 400 });
      password = body.password;
      return new HttpResponse(null, { status: 204 });
    }),
    http.patch("*/api/auth/me", async ({ request }) => {
      const body = (await request.json()) as Schemas["UpdateProfileRequest"];
      requests.push({ route: "update-profile", body });
      const session = current ?? adaSession;
      current = { ...session, member: { ...session.member, name: body.name.trim() } };
      return HttpResponse.json(current);
    }),
    http.post("*/api/auth/me/password", async ({ request }) => {
      const body = (await request.json()) as Schemas["ChangePasswordRequest"];
      requests.push({ route: "change-password", body });
      if (body.current_password !== password) return HttpResponse.json(wrongCurrentPassword, { status: 400 });
      password = body.new_password;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  return { requests };
}
