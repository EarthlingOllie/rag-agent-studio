import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import { adaSession } from "./auth";
import { server } from "./server";

export type OrganisationMember = Schemas["OrganisationMemberOut"];

export const LAST_OWNER = "An Organisation needs at least one Owner. Make someone else an Owner first.";

export const adaMember: OrganisationMember = { ...adaSession.member, role: "owner", joined_at: "2026-05-01T09:30:00Z" };
export const graceMember: OrganisationMember = {
  id: "6a1b0c58-0d6e-4c1b-9d1e-1f1a6c0f0a02",
  name: "Grace Hopper",
  email: "grace@example.test",
  role: "editor",
  joined_at: "2026-06-01T09:30:00Z",
};
export const charlesMember: OrganisationMember = {
  id: "6a1b0c58-0d6e-4c1b-9d1e-1f1a6c0f0a03",
  name: "Charles Babbage",
  email: "charles@example.test",
  role: "owner",
  joined_at: "2026-06-02T09:30:00Z",
};

/**
 * A stateful stand-in for the Members API: role changes and removals change the list, and
 * leaving or demoting the last Owner is refused as on the real API. Records what it receives.
 */
export function fakeMembersApi(options: { members?: OrganisationMember[] } = {}) {
  let members = [...(options.members ?? [adaMember, graceMember])];
  const roleChanges: { memberId: string; role: string }[] = [];
  const removed: string[] = [];
  let left = 0;
  const owners = () => members.filter((member) => member.role === "owner").length;
  const lastOwner = () => HttpResponse.json({ detail: LAST_OWNER }, { status: 409 });
  const isLastOwner = (id: string) => owners() === 1 && members.find((m) => m.id === id)?.role === "owner";
  server.use(
    http.get("*/api/organisations/:organisationId/members", () => HttpResponse.json(members)),
    http.patch("*/api/organisations/:organisationId/members/:memberId", async ({ params, request }) => {
      const { role } = (await request.json()) as Schemas["ChangeRoleRequest"];
      const memberId = params.memberId as string;
      roleChanges.push({ memberId, role });
      if (role === "editor" && isLastOwner(memberId)) return lastOwner();
      members = members.map((member) => (member.id === memberId ? { ...member, role } : member));
      return HttpResponse.json(members.find((member) => member.id === memberId));
    }),
    http.delete("*/api/organisations/:organisationId/members/:memberId", ({ params }) => {
      const memberId = params.memberId as string;
      removed.push(memberId);
      if (isLastOwner(memberId)) return lastOwner();
      members = members.filter((member) => member.id !== memberId);
      return new HttpResponse(null, { status: 204 });
    }),
    http.post("*/api/organisations/:organisationId/leave", () => {
      left += 1;
      if (isLastOwner(adaSession.member.id)) return lastOwner();
      return new HttpResponse(null, { status: 204 });
    }),
  );
  return {
    roleChanges,
    removed,
    get left() {
      return left;
    },
  };
}
