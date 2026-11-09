import { Link, Navigate, Outlet, useLocation, useParams } from "@tanstack/react-router";
import { useState } from "react";

import { type Session, useMe } from "../auth/session";
import { AppearanceToggle, Brand, layout, TopBar } from "../design";
import { AccountMenu } from "./AccountMenu";
import { StudioBreadcrumb } from "./StudioBreadcrumb";
import { TopBarSlot } from "./TopBarActions";

function Centered({ children, role }: { children: string; role: "status" | "alert" }) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-canvas text-ink">
      <p role={role}>{children}</p>
    </main>
  );
}

/** Everything a signed-in Member sees. Signed-out visitors are sent to the sign-in screen. */
export function SignedInShell() {
  const me = useMe();
  if (me.isPending) return <Centered role="status">Loading…</Centered>;
  if (me.isError) return <Centered role="alert">The Studio could not reach the API. Try again shortly.</Centered>;
  if (me.data === null) return <Navigate to="/sign-in" />;
  return <Outlet />;
}

/** `/`: opens the active Organisation: the one the Member last switched to, or their first. */
export function HomeRedirect() {
  const { data } = useMe();
  const active = (data as Session).active_organisation_id;
  if (active === null) {
    return <Centered role="status">You don't belong to any Organisation yet.</Centered>;
  }
  return <Navigate to="/organisations/$organisationId/projects" params={{ organisationId: active }} />;
}

/** The Studio frame for one Organisation: the top bar, whose breadcrumb is the navigation, and the page. */
export function OrganisationShell() {
  const { data } = useMe();
  const session = data as Session;
  const { organisationId } = useParams({ from: "/signed-in/organisations/$organisationId" });
  const organisation = session.organisations.find((candidate) => candidate.id === organisationId);
  // The Require MFA policy: until the Member turns MFA on, the Organisation offers only enrolment.
  const mustEnrol = organisation !== undefined && organisation.mfa_required && !session.member.mfa_enabled;
  const onSecurityPage = useLocation().pathname.endsWith("/security");
  // The page's own top bar actions are portalled into this element (`TopBarActions`).
  const [slot, setSlot] = useState<HTMLDivElement | null>(null);

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <TopBar
        home={
          <Link to="/" aria-label="Studio home" className="rounded-md">
            <Brand />
          </Link>
        }
        breadcrumb={<StudioBreadcrumb session={session} organisationId={organisationId} mustEnrol={mustEnrol} />}
        actions={
          <>
            <div ref={setSlot} className="flex items-center gap-3 empty:hidden" />
            <AppearanceToggle />
            <AccountMenu session={session} organisationId={organisationId} inOrganisation={organisation !== undefined} />
          </>
        }
      />
      <main className={layout.page}>
        {organisation ? (
          mustEnrol && !onSecurityPage ? (
            <Navigate to="/organisations/$organisationId/security" params={{ organisationId }} replace />
          ) : (
            <TopBarSlot.Provider value={slot}>
              <Outlet />
            </TopBarSlot.Provider>
          )
        ) : (
          <>
            <h1 className="text-2xl font-semibold">Organisation not found</h1>
            <p className="mt-2 text-muted">
              It doesn't exist, or you are not a Member of it. <Link to="/" className="underline">Go to your Organisation</Link>
            </p>
          </>
        )}
      </main>
    </div>
  );
}
