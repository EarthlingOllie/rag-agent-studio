import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import { adaSession, type Session } from "./auth";
import { graceInvite, type Invite } from "./invites";
import { server } from "./server";

export const analyticalEngines = adaSession.organisations[0] as Schemas["MembershipOut"];
export const differenceEngines: Schemas["MembershipOut"] = {
  id: "0b6f3a3e-6f53-4a5e-9a39-6d2b8f0c1e09",
  name: "Difference Engines",
  role: "owner",
  mfa_required: false,
};

/** Ada, who owns two Organisations; `active` is the one the API remembers. */
export function adaInTwo(active = analyticalEngines.id): Session {
  return { ...adaSession, organisations: [analyticalEngines, differenceEngines], active_organisation_id: active };
}

/** Each Organisation's own pending invite: only Difference Engines invited Charles. */
export const invitesByOrganisation: Record<string, Invite[]> = {
  [analyticalEngines.id]: [graceInvite],
  [differenceEngines.id]: [{ ...graceInvite, id: "c0000000-0000-4000-8000-000000000009", email: "charles@example.test" }],
};

/**
 * A stand-in for the switcher: `me` reports the remembered Organisation, switching changes it
 * (or fails with `failWith`) and each Organisation lists only its own invites.
 */
export function fakeSwitcherApi(session: Session, options: { failWith?: number } = {}) {
  let current = session;
  const switches: unknown[] = [];
  server.use(
    http.get("*/api/auth/me", () => HttpResponse.json(current)),
    http.put("*/api/auth/me/active-organisation", async ({ request }) => {
      const body = (await request.json()) as Schemas["SwitchOrganisationRequest"];
      switches.push(body);
      if (options.failWith !== undefined) return new HttpResponse(null, { status: options.failWith });
      current = { ...current, active_organisation_id: body.organisation_id };
      return HttpResponse.json(current);
    }),
    http.get("*/api/organisations/:organisationId/invites", ({ params }) =>
      HttpResponse.json(invitesByOrganisation[params.organisationId as string] ?? []),
    ),
  );
  return { switches };
}
