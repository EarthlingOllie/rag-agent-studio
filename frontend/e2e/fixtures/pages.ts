/**
 * Every signed-in page of the Studio, by its route, in the order a Member meets them. The axe
 * sweep (`e2e/tests/accessibility.spec.ts`) visits each in the light and the dark Appearance;
 * `apps/studio/src/signedInPages.test.ts` fails when the router gains a page this list lacks.
 */
const ORGANISATION = "/organisations/$organisationId";
const PROJECT = `${ORGANISATION}/projects/$projectId`;
const AGENT = `${PROJECT}/agents/$agentId`;

export interface SignedInPage {
  /** A short name for reports and screenshots. */
  name: string;
  /** The router's path, with `$parameters`. */
  route: string;
}

export const SIGNED_IN_PAGES: SignedInPage[] = [
  { name: "projects", route: `${ORGANISATION}/projects` },
  { name: "documents", route: PROJECT },
  { name: "document-viewer", route: `${PROJECT}/documents/$documentId` },
  { name: "instructions", route: `${PROJECT}/instructions` },
  { name: "agents", route: `${PROJECT}/agents` },
  { name: "agent-playground", route: AGENT },
  { name: "agent-versions", route: `${AGENT}/versions` },
  { name: "agent-embed", route: `${AGENT}/embed` },
  { name: "agent-conversations", route: `${AGENT}/conversations` },
  { name: "agent-conversation", route: `${AGENT}/conversations/$conversationId` },
  { name: "conversations", route: `${PROJECT}/conversations` },
  { name: "conversation", route: `${PROJECT}/conversations/$conversationId` },
  { name: "analytics", route: `${PROJECT}/analytics` },
  { name: "project-settings", route: `${PROJECT}/settings` },
  { name: "cost", route: `${ORGANISATION}/cost` },
  { name: "settings-general", route: `${ORGANISATION}/settings` },
  { name: "settings-members", route: `${ORGANISATION}/settings/members` },
  { name: "settings-credentials", route: `${ORGANISATION}/settings/credentials` },
  { name: "settings-models", route: `${ORGANISATION}/settings/models` },
  { name: "settings-theme", route: `${ORGANISATION}/settings/theme` },
  { name: "settings-audit", route: `${ORGANISATION}/settings/audit` },
  { name: "profile", route: `${ORGANISATION}/profile` },
  { name: "security", route: `${ORGANISATION}/security` },
];

/** The ids a page's route needs: those it doesn't name are ignored. */
export type PageIds = Partial<Record<"organisationId" | "projectId" | "documentId" | "agentId" | "conversationId", string>>;

/** A page's address, its `$parameters` filled from `ids`. Throws when one is missing. */
export function pagePath(page: SignedInPage, ids: PageIds): string {
  return page.route.replace(/\$(\w+)/g, (_, name: string) => {
    const value = ids[name as keyof PageIds];
    if (value === undefined) throw new Error(`${page.name} needs ${name}`);
    return value;
  });
}

/** The two Appearances every page is checked in. */
export const APPEARANCES = ["light", "dark"] as const;
