import {
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  type RouterHistory,
} from "@tanstack/react-router";

import { SignedOutFrame } from "./auth/AuthLayout";
import { MfaChallengePage } from "./auth/MfaChallengePage";
import { ForgotPasswordPage } from "./auth/ForgotPasswordPage";
import { ResetPasswordPage } from "./auth/ResetPasswordPage";
import { SignInPage } from "./auth/SignInPage";
import { SignUpPage } from "./auth/SignUpPage";
import { CostPage } from "./cost/CostPage";
import { AcceptInvitePage } from "./invites/AcceptInvitePage";
import {
  AuditSettingsPage,
  CredentialsSettingsPage,
  GeneralSettingsPage,
  MembersSettingsPage,
  ModelsSettingsPage,
  OrganisationSettingsLayout,
  ThemeSettingsPage,
} from "./settings/OrganisationSettings";
import { AgentEmbedView, AgentEvaluationView, AgentPage, AgentPlaygroundView, AgentVersionsView } from "./projects/AgentPage";
import { AgentsTab } from "./projects/AgentsTab";
import { AnalyticsTab } from "./projects/AnalyticsTab";
import { ProjectLayout } from "./projects/ProjectPage";
import {
  AgentConversationsView,
  agentConversationFilters,
  ConversationPage,
  ConversationsTab,
  NoConversationChosen,
} from "./projects/ConversationsTab";
import { conversationFilters } from "./projects/conversations";
import { DocumentsTab } from "./projects/DocumentsTab";
import { ProjectSettingsTab } from "./projects/ProjectSettingsTab";
import { DocumentViewer } from "./projects/DocumentViewer";
import { InstructionsTab } from "./projects/InstructionsTab";
import { ProjectsPage } from "./projects/ProjectsPage";
import { HomeRedirect, OrganisationShell, SignedInShell } from "./shell/SignedInShell";
import { ProfilePage } from "./profile/ProfilePage";
import { SecurityPage } from "./security/SecurityPage";
import { StatusPage } from "./status/StatusPage";

/** The status page is public: the signed-out panel, its mark linking to the Studio. */
function StatusLayout() {
  return (
    <SignedOutFrame home wide>
      <StatusPage />
    </SignedOutFrame>
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
const projectsRoute = createRoute({
  getParentRoute: () => organisationRoute,
  path: "/projects",
  // After a permanent deletion the page says which Project is being deleted, as `?deleted=`.
  validateSearch: (search: Record<string, unknown>): { deleted?: string } =>
    typeof search.deleted === "string" ? { deleted: search.deleted } : {},
  component: ProjectsPage,
});
const projectRoute = createRoute({
  getParentRoute: () => organisationRoute,
  path: "/projects/$projectId",
  component: ProjectLayout,
});
const documentsTabRoute = createRoute({ getParentRoute: () => projectRoute, path: "/", component: DocumentsTab });
const documentViewerRoute = createRoute({
  getParentRoute: () => projectRoute,
  path: "/documents/$documentId",
  component: DocumentViewer,
});
const instructionsTabRoute = createRoute({
  getParentRoute: () => projectRoute,
  path: "/instructions",
  component: InstructionsTab,
});
const agentsTabRoute = createRoute({
  getParentRoute: () => projectRoute,
  path: "/agents",
  // After a permanent deletion the tab says which Agent was deleted, as `?deleted=`.
  validateSearch: (search: Record<string, unknown>): { deleted?: string } =>
    typeof search.deleted === "string" ? { deleted: search.deleted } : {},
  component: AgentsTab,
});
const agentRoute = createRoute({ getParentRoute: () => projectRoute, path: "/agents/$agentId", component: AgentPage });
// An Agent's views, switched in the breadcrumb.
const agentPlaygroundRoute = createRoute({ getParentRoute: () => agentRoute, path: "/", component: AgentPlaygroundView });
const agentVersionsRoute = createRoute({ getParentRoute: () => agentRoute, path: "/versions", component: AgentVersionsView });
const agentEvaluationRoute = createRoute({
  getParentRoute: () => agentRoute,
  path: "/evaluation",
  component: AgentEvaluationView,
});
const agentEmbedRoute = createRoute({ getParentRoute: () => agentRoute, path: "/embed", component: AgentEmbedView });
// The Agent's Conversations: the Project's list fixed to the Agent, beside the open Conversation.
const agentConversationsRoute = createRoute({
  getParentRoute: () => agentRoute,
  path: "/conversations",
  validateSearch: agentConversationFilters,
  component: AgentConversationsView,
});
const agentConversationsIndexRoute = createRoute({
  getParentRoute: () => agentConversationsRoute,
  path: "/",
  component: NoConversationChosen,
});
const agentConversationRoute = createRoute({
  getParentRoute: () => agentConversationsRoute,
  path: "/$conversationId",
  component: ConversationPage,
});
// The Project's Conversations: the list, filtered by its URL so the filters survive opening a
// Conversation, with the open one beside it.
const conversationsTabRoute = createRoute({
  getParentRoute: () => projectRoute,
  path: "/conversations",
  validateSearch: conversationFilters,
  component: ConversationsTab,
});
const conversationsIndexRoute = createRoute({ getParentRoute: () => conversationsTabRoute, path: "/", component: NoConversationChosen });
const conversationRoute = createRoute({
  getParentRoute: () => conversationsTabRoute,
  path: "/$conversationId",
  component: ConversationPage,
});
// Analytics is filtered to one Agent, as `?agent=` (each Agent's views link to it).
const analyticsTabRoute = createRoute({
  getParentRoute: () => projectRoute,
  path: "/analytics",
  validateSearch: (search: Record<string, unknown>): { agent?: string } =>
    typeof search.agent === "string" && search.agent !== "" ? { agent: search.agent } : {},
  component: AnalyticsTab,
});
const projectSettingsTabRoute = createRoute({ getParentRoute: () => projectRoute, path: "/settings", component: ProjectSettingsTab });
const costRoute = createRoute({ getParentRoute: () => organisationRoute, path: "/cost", component: CostPage });
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
const credentialsSettingsRoute = createRoute({
  getParentRoute: () => settingsRoute,
  path: "/credentials",
  component: CredentialsSettingsPage,
});
const modelsSettingsRoute = createRoute({ getParentRoute: () => settingsRoute, path: "/models", component: ModelsSettingsPage });
const themeSettingsRoute = createRoute({ getParentRoute: () => settingsRoute, path: "/theme", component: ThemeSettingsPage });
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
      projectRoute.addChildren([
        documentsTabRoute,
        documentViewerRoute,
        instructionsTabRoute,
        agentsTabRoute,
        agentRoute.addChildren([
          agentPlaygroundRoute,
          agentVersionsRoute,
          agentEvaluationRoute,
          agentEmbedRoute,
          agentConversationsRoute.addChildren([agentConversationsIndexRoute, agentConversationRoute]),
        ]),
        conversationsTabRoute.addChildren([conversationsIndexRoute, conversationRoute]),
        analyticsTabRoute,
        projectSettingsTabRoute,
      ]),
      costRoute,
      settingsRoute.addChildren([generalSettingsRoute, credentialsSettingsRoute, modelsSettingsRoute, themeSettingsRoute, membersSettingsRoute, auditSettingsRoute]),
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
