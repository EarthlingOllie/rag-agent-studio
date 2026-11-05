import { Link, Outlet, useParams } from "@tanstack/react-router";

import { type Session, useMe } from "../auth/session";
import { AuditPage } from "./AuditPage";
import { MembersPage } from "./MembersPage";

const TAB = "rounded px-3 py-2 text-sm text-slate-700 hover:bg-slate-100 [&.active]:bg-slate-100 [&.active]:font-medium [&.active]:text-slate-900";

function useOrganisation() {
  const { organisationId } = useParams({ from: "/signed-in/organisations/$organisationId" });
  const session = useMe().data as Session;
  // OrganisationShell renders settings only for an Organisation the Member belongs to.
  const role = session.organisations.find((organisation) => organisation.id === organisationId)?.role;
  return { organisationId, isOwner: role === "owner" };
}

/** Organisation settings, with a tab per area. The Members and Audit tabs are shown to Owners only. */
export function OrganisationSettingsLayout() {
  const { organisationId, isOwner } = useOrganisation();
  return (
    <section aria-labelledby="page-heading">
      <h1 id="page-heading" className="text-2xl font-semibold">
        Organisation settings
      </h1>
      <nav aria-label="Organisation settings" className="mt-4 flex gap-2 border-b border-slate-200 pb-2">
        <Link to="/organisations/$organisationId/settings" params={{ organisationId }} activeOptions={{ exact: true }} className={TAB}>
          General
        </Link>
        {isOwner && (
          <>
            <Link to="/organisations/$organisationId/settings/members" params={{ organisationId }} className={TAB}>
              Members
            </Link>
            <Link to="/organisations/$organisationId/settings/audit" params={{ organisationId }} className={TAB}>
              Audit
            </Link>
          </>
        )}
      </nav>
      <div className="mt-6">
        <Outlet />
      </div>
    </section>
  );
}

export function GeneralSettingsPage() {
  return <p className="text-slate-700">Members, roles and security settings will appear here.</p>;
}

export function AuditSettingsPage() {
  const { organisationId, isOwner } = useOrganisation();
  return <AuditPage organisationId={organisationId} isOwner={isOwner} />;
}

export function MembersSettingsPage() {
  const { organisationId, isOwner } = useOrganisation();
  return <MembersPage organisationId={organisationId} isOwner={isOwner} />;
}
