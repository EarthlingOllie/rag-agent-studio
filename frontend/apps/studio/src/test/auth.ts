import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import { notSignedIn, server } from "./server";

export type Session = Schemas["SessionResponse"];

export const adaSession: Session = {
  member: { id: "6a1b0c58-0d6e-4c1b-9d1e-1f1a6c0f0a01", name: "Ada Lovelace", email: "ada@example.test" },
  organisations: [{ id: "0b6f3a3e-6f53-4a5e-9a39-6d2b8f0c1e02", name: "Analytical Engines", role: "owner" }],
  active_organisation_id: "0b6f3a3e-6f53-4a5e-9a39-6d2b8f0c1e02",
};

/**
 * A stateful stand-in for the auth API: sign-up and sign-in start a session that `me` then
 * reports, and sign-out ends it. Returns the requests it received, for assertions on bodies.
 */
export function fakeAuthApi(options: { signedInAs?: Session; account?: Session } = {}) {
  let current: Session | undefined = options.signedInAs;
  const account = options.account ?? adaSession;
  const requests: { route: string; body: unknown }[] = [];

  server.use(
    http.get("*/api/auth/me", () =>
      current ? HttpResponse.json(current) : HttpResponse.json(notSignedIn, { status: 401 }),
    ),
    http.post("*/api/auth/sign-up", async ({ request }) => {
      requests.push({ route: "sign-up", body: await request.json() });
      current = account;
      return HttpResponse.json(account, { status: 201 });
    }),
    http.post("*/api/auth/sign-in", async ({ request }) => {
      requests.push({ route: "sign-in", body: await request.json() });
      current = account;
      return HttpResponse.json(account);
    }),
    http.post("*/api/auth/sign-out", () => {
      requests.push({ route: "sign-out", body: null });
      current = undefined;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  return { requests };
}
