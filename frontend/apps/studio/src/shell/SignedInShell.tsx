import { Link, Navigate, Outlet, useLocation, useParams } from "@tanstack/react-router";

import { SignedOutFrame } from "../auth/AuthLayout";
import { type Session, useMe } from "../auth/session";
import { AppearanceToggle, Brand, button, EmptyState, layout, Notice, Skeleton, TopBar } from "../design";
import { AccountMenu } from "./AccountMenu";
import { StudioBreadcrumb } from "./StudioBreadcrumb";

/** Everything a signed-in Member sees. Signed-out visitors are sent to the sign-in screen. */
export function SignedInShell() {
  const me = useMe();
  // Before the session is known there is no top bar to show, so these sit in the signed-out panel.
  if (me.isPending) {
    return (
      <SignedOutFrame>
        <Skeleton label="Loading the Studio" />
      </SignedOutFrame>
    );
  }
  if (me.isError) {
    return (
      <SignedOutFrame>
        <Notice tone="error">The Studio could not reach the API. Try again shortly.</Notice>
      </SignedOutFrame>
    );
  }
  if (me.data === null) return <Navigate to="/sign-in" />;
  return <Outlet />;
}

/** `/`: opens the active Organisation: the one the Member last switched to, or their first. */
export function HomeRedirect() {
  const { data } = useMe();
  const active = (data as Session).active_organisation_id;
  if (active === null) {
    return (
      <SignedOutFrame wide>
        <EmptyState
          icon="projects"
          title="You don't belong to any Organisation yet."
          description="Ask an Owner to invite you, then open the link in their email."
        />
      </SignedOutFrame>
    );
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
            <Outlet />
          )
        ) : (
          <EmptyState
            icon="warning"
            title="Organisation not found"
            description="It doesn't exist, or you are not a Member of it."
            action={
              <Link to="/" className={button.primary}>
                Go to your Organisation
              </Link>
            }
          />
        )}
      </main>
    </div>
  );
}
