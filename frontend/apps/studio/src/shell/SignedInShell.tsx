import { Link, Navigate, Outlet, useLocation, useParams } from "@tanstack/react-router";
import { useId, useRef, useState } from "react";

import { SignedOutFrame } from "../auth/AuthLayout";
import { type Session, useMe } from "../auth/session";
import { AppearanceToggle, Brand, button, EmptyState, layout, Notice, SidebarButton, Skeleton, TopBar } from "../design";
import { AccountMenu } from "./AccountMenu";
import { StudioBreadcrumb } from "./StudioBreadcrumb";
import { StudioSidebar } from "./StudioSidebar";
import { TopBarSlot } from "./TopBarActions";

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

/**
 * The Studio frame for one Organisation: the top bar (the mark, the breadcrumb, the page's actions
 * and the Member's controls), then the sidebar, which is the navigation, beside the page. Below
 * `md` the sidebar is a drawer that the top bar's "Open navigation" button opens.
 */
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
  // Below `md` the sidebar is a drawer behind the top bar's button, which takes focus back on close.
  const sidebarId = useId();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const drawerButton = useRef<HTMLButtonElement>(null);
  const closeDrawer = () => {
    setDrawerOpen(false);
    drawerButton.current?.focus();
  };

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <TopBar
        menu={
          <SidebarButton
            ref={drawerButton}
            controls={sidebarId}
            open={drawerOpen}
            onOpen={() => {
              setDrawerOpen(true);
            }}
          />
        }
        home={
          <Link to="/" aria-label="Studio home" className="rounded-md">
            <Brand />
          </Link>
        }
        breadcrumb={organisation && <StudioBreadcrumb organisationId={organisationId} />}
        actions={
          <>
            <div ref={setSlot} className="flex items-center gap-3 empty:hidden" />
            <AppearanceToggle />
            <AccountMenu session={session} organisationId={organisationId} inOrganisation={organisation !== undefined} />
          </>
        }
      />
      <div className="md:flex">
        <StudioSidebar
          session={session}
          organisationId={organisationId}
          mustEnrol={mustEnrol}
          id={sidebarId}
          drawer={{ open: drawerOpen, onClose: closeDrawer }}
        />
        {/* The page keeps its 1160 px column, centred in the space beside the sidebar. */}
        <main className={`${layout.page} min-w-0`}>
          {organisation ? (
            mustEnrol && !onSecurityPage ? (
              <Navigate to="/organisations/$organisationId/security" params={{ organisationId }} replace />
            ) : (
              <TopBarSlot.Provider value={slot}>
                <Outlet />
              </TopBarSlot.Provider>
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
    </div>
  );
}
