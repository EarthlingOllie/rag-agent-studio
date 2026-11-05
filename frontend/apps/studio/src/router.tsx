import {
  createRootRoute,
  createRoute,
  createRouter,
  Link,
  Outlet,
  type RouterHistory,
} from "@tanstack/react-router";

import { MfaChallengePage } from "./auth/MfaChallengePage";
import { ForgotPasswordPage } from "./auth/ForgotPasswordPage";
import { ResetPasswordPage } from "./auth/ResetPasswordPage";
import { SignInPage } from "./auth/SignInPage";
import { SignUpPage } from "./auth/SignUpPage";
import { AcceptInvitePage } from "./invites/AcceptInvitePage";
import {
  AuditSettingsPage,
  GeneralSettingsPage,
  MembersSettingsPage,
  OrganisationSettingsLayout,
} from "./settings/OrganisationSettings";
import { HomeRedirect, OrganisationShell, ProjectsPage, SignedInShell } from "./shell/SignedInShell";
import { ProfilePage } from "./profile/ProfilePage";
import { SecurityPage } from "./security/SecurityPage";
import { StatusPage } from "./status/StatusPage";

function StatusLayout() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <nav className="mx-auto flex max-w-4xl items-center gap-6 px-6 py-4" aria-label="Main">
          <Link to="/" className="font-semibold">
            RAG Agent Studio
          </Link>
        </nav>
      </header>
      <main className="mx-auto max-w-4xl px-6 py-8">
        <StatusPage />
      </main>
    </div>
  );
}

const rootRoute = createRootRoute({ component: Outlet });
const statusRoute = createRoute({ getParentRoute: () => rootRoute, path: "/status", component: StatusLayout });
const signUpRoute = createRoute({ getParentRoute: () => rootRoute, path: "/sign-up", component: SignUpPage });
const signInRoute = createRoute({ getParentRoute: () => rootRoute, path: "/sign-in", component: SignInPage });
const mfaChallengeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/sign-in/mfa",
  component: MfaChallengePage,
});
const forgotPasswordRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/forgot-password",
  component: ForgotPasswordPage,
});
const resetPasswordRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/reset-password",
  // The emailed link carries the token as `?token=`.
  validateSearch: (search: Record<string, unknown>): { token?: string } =>
    typeof search.token === "string" ? { token: search.token } : {},
  component: ResetPasswordPage,
});
const acceptInviteRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/accept-invite",
  // The invite link carries the token as `?token=`.
  validateSearch: (search: Record<string, unknown>): { token?: string } =>
    typeof search.token === "string" ? { token: search.token } : {},
  component: AcceptInvitePage,
});
const signedInRoute = createRoute({ getParentRoute: () => rootRoute, id: "signed-in", component: SignedInShell });
const homeRoute = createRoute({ getParentRoute: () => signedInRoute, path: "/", component: HomeRedirect });
const organisationRoute = createRoute({
  getParentRoute: () => signedInRoute,
  path: "/organisations/$organisationId",
  component: OrganisationShell,
});
const projectsRoute = createRoute({ getParentRoute: () => organisationRoute, path: "/projects", component: ProjectsPage });
const profileRoute = createRoute({ getParentRoute: () => organisationRoute, path: "/profile", component: ProfilePage });
const settingsRoute = createRoute({
  getParentRoute: () => organisationRoute,
  path: "/settings",
  component: OrganisationSettingsLayout,
});
const generalSettingsRoute = createRoute({ getParentRoute: () => settingsRoute, path: "/", component: GeneralSettingsPage });
const membersSettingsRoute = createRoute({
  getParentRoute: () => settingsRoute,
  path: "/members",
  component: MembersSettingsPage,
});
const auditSettingsRoute = createRoute({ getParentRoute: () => settingsRoute, path: "/audit", component: AuditSettingsPage });

const securityRoute = createRoute({
  getParentRoute: () => organisationRoute,
  path: "/security",
  component: SecurityPage,
});

const routeTree = rootRoute.addChildren([
  statusRoute,
  signUpRoute,
  signInRoute,
  mfaChallengeRoute,
  forgotPasswordRoute,
  resetPasswordRoute,
  acceptInviteRoute,
  signedInRoute.addChildren([
    homeRoute,
    organisationRoute.addChildren([
      projectsRoute,
      settingsRoute.addChildren([generalSettingsRoute, membersSettingsRoute, auditSettingsRoute]),
      profileRoute,
      securityRoute,
    ]),
  ]),
]);

export function createAppRouter(history?: RouterHistory) {
  return createRouter(history ? { routeTree, history } : { routeTree });
}

export type AppRouter = ReturnType<typeof createAppRouter>;

declare module "@tanstack/react-router" {
  interface Register {
    router: AppRouter;
  }
}
