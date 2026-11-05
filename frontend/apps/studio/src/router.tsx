import {
  createRootRoute,
  createRoute,
  createRouter,
  Link,
  Outlet,
  type RouterHistory,
} from "@tanstack/react-router";

import { MfaChallengePage } from "./auth/MfaChallengePage";
import { SignInPage } from "./auth/SignInPage";
import { SignUpPage } from "./auth/SignUpPage";
import {
  HomeRedirect,
  OrganisationSettingsPage,
  OrganisationShell,
  ProjectsPage,
  SignedInShell,
} from "./shell/SignedInShell";
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
const signedInRoute = createRoute({ getParentRoute: () => rootRoute, id: "signed-in", component: SignedInShell });
const homeRoute = createRoute({ getParentRoute: () => signedInRoute, path: "/", component: HomeRedirect });
const organisationRoute = createRoute({
  getParentRoute: () => signedInRoute,
  path: "/organisations/$organisationId",
  component: OrganisationShell,
});
const projectsRoute = createRoute({ getParentRoute: () => organisationRoute, path: "/projects", component: ProjectsPage });
const settingsRoute = createRoute({
  getParentRoute: () => organisationRoute,
  path: "/settings",
  component: OrganisationSettingsPage,
});

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
  signedInRoute.addChildren([homeRoute, organisationRoute.addChildren([projectsRoute, settingsRoute, securityRoute])]),
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
