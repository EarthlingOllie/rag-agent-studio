import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import type { Session } from "./auth";
import { server } from "./server";

export const OWNER_WITHOUT_MFA = "Turn on MFA for your own account before requiring it.";

/**
 * A stateful stand-in for the Require MFA policy: `me` reports the policy, and setting it
 * changes it, unless the Member has no MFA and asks to require it (409, as the API answers).
 * Returns the request bodies it received.
 */
export function fakeMfaPolicyApi(session: Session) {
  let current = session;
  const requests: Schemas["MfaPolicyRequest"][] = [];
  server.use(
    http.get("*/api/auth/me", () => HttpResponse.json(current)),
    http.put("*/api/organisations/:organisationId/mfa-policy", async ({ params, request }) => {
      const body = (await request.json()) as Schemas["MfaPolicyRequest"];
      requests.push(body);
      if (body.require_mfa && !current.member.mfa_enabled) {
        return HttpResponse.json({ detail: OWNER_WITHOUT_MFA }, { status: 409 });
      }
      current = {
        ...current,
        organisations: current.organisations.map((organisation) =>
          organisation.id === params.organisationId ? { ...organisation, mfa_required: body.require_mfa } : organisation,
        ),
      };
      const organisation = current.organisations.find((candidate) => candidate.id === params.organisationId);
      return HttpResponse.json({
        id: organisation?.id,
        name: organisation?.name,
        role: organisation?.role,
        require_mfa: body.require_mfa,
      });
    }),
  );
  return { requests };
}
