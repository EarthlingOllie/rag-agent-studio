import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import { adaSession, type Session } from "./auth";
import { server } from "./server";

export type Invite = Schemas["InviteOut"];
export type InvitePreview = Schemas["InvitePreviewOut"];

const ada = adaSession.member;
export const organisationId = adaSession.organisations[0]?.id ?? "";

export const graceInvite: Invite = {
  id: "c0000000-0000-4000-8000-000000000001",
  email: "grace@example.test",
  role: "editor",
  created_at: "2026-06-01T09:30:00Z",
  expires_at: "2026-06-08T09:30:00Z",
  expired: false,
  invited_by: ada,
};

export const expiredInvite: Invite = {
  id: "c0000000-0000-4000-8000-000000000002",
  email: "charles@example.test",
  role: "owner",
  created_at: "2026-05-01T09:30:00Z",
  expires_at: "2026-05-08T09:30:00Z",
  expired: true,
  invited_by: ada,
};

const STUDIO = "https://studio.example.test";

export function linkFor(token: string): string {
  return `${STUDIO}/accept-invite?token=${token}`;
}

/**
 * A stateful stand-in for the Owner's invite API: creating adds a pending invite, revoking
 * removes it and renewing gives it a new link. Records the bodies it receives.
 */
export function fakeInvitesApi(options: { pending?: Invite[]; emailSent?: boolean } = {}) {
  let pending = [...(options.pending ?? [graceInvite, expiredInvite])];
  let issued = 0;
  const created: unknown[] = [];
  const revoked: string[] = [];
  const renewed: string[] = [];
  server.use(
    http.get("*/api/organisations/:organisationId/invites", () => HttpResponse.json(pending)),
    http.post("*/api/organisations/:organisationId/invites", async ({ request }) => {
      const body = (await request.json()) as Schemas["CreateInviteRequest"];
      created.push(body);
      if (pending.some((invite) => invite.email === body.email)) {
        return HttpResponse.json(
          { detail: "That email already has a pending invite. Copy a new link or revoke it." },
          { status: 409 },
        );
      }
      issued += 1;
      const invite: Invite = {
        ...graceInvite,
        id: `c0000000-0000-4000-8000-00000000010${String(issued)}`,
        email: body.email,
        role: body.role,
      };
      pending = [invite, ...pending];
      return HttpResponse.json(
        { invite, link: linkFor(`new-token-${String(issued)}`), email_sent: body.send_email && (options.emailSent ?? true) },
        { status: 201 },
      );
    }),
    http.delete("*/api/organisations/:organisationId/invites/:inviteId", ({ params }) => {
      revoked.push(params.inviteId as string);
      pending = pending.filter((invite) => invite.id !== params.inviteId);
      return new HttpResponse(null, { status: 204 });
    }),
    http.post("*/api/organisations/:organisationId/invites/:inviteId/renew", ({ params }) => {
      renewed.push(params.inviteId as string);
      issued += 1;
      pending = pending.map((invite) =>
        invite.id === params.inviteId ? { ...invite, expired: false, expires_at: "2026-06-20T09:30:00Z" } : invite,
      );
      const invite = pending.find((candidate) => candidate.id === params.inviteId) as Invite;
      return HttpResponse.json({ invite, link: linkFor(`renewed-token-${String(issued)}`), email_sent: false });
    }),
  );
  return { created, revoked, renewed };
}

export const invitedOrganisation = { id: "0b6f3a3e-6f53-4a5e-9a39-6d2b8f0c1e99", name: "Difference Engines" };

export function previewFor(email: string, overrides: Partial<InvitePreview> = {}): InvitePreview {
  return {
    organisation_id: invitedOrganisation.id,
    organisation_name: invitedOrganisation.name,
    email,
    role: "editor",
    invited_by_name: "Charles Babbage",
    account_exists: false,
    ...overrides,
  };
}

/** The session a Member has after joining the invited Organisation. */
export function joined(session: Session, role: "owner" | "editor" = "editor"): Session {
  return { ...session, organisations: [...session.organisations, { ...invitedOrganisation, role, mfa_required: false }] };
}

/**
 * A stand-in for the invited person's side: looking up `token` gives `preview`; accepting or
 * signing up answers with `session` (or the given status) and records the request bodies.
 */
export function fakeAcceptApi(options: {
  token: string;
  preview: InvitePreview | { status: number };
  accepted?: Session | { status: number };
}) {
  const requests: { route: string; body: unknown }[] = [];
  const answer = async (route: string, request: Request, created: boolean) => {
    requests.push({ route, body: await request.json() });
    const accepted = options.accepted;
    if (accepted === undefined || "status" in accepted) {
      const status = accepted?.status ?? 500;
      return HttpResponse.json({ detail: "refused" }, { status });
    }
    // From now on the session is the one that joined, as on the real API.
    server.use(http.get("*/api/auth/me", () => HttpResponse.json(accepted)));
    return HttpResponse.json(accepted, { status: created ? 201 : 200 });
  };
  server.use(
    http.post("*/api/invites/lookup", async ({ request }) => {
      const { token } = (await request.json()) as { token: string };
      const preview = options.preview;
      if ("status" in preview) return HttpResponse.json({ detail: "nope" }, { status: preview.status });
      if (token !== options.token) return HttpResponse.json({ detail: "nope" }, { status: 404 });
      return HttpResponse.json(preview);
    }),
    http.post("*/api/invites/accept", ({ request }) => answer("accept", request, false)),
    http.post("*/api/invites/sign-up", ({ request }) => answer("sign-up", request, true)),
  );
  return { requests };
}
