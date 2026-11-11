import { createLink, useMatchRoute } from "@tanstack/react-router";
import type { AnchorHTMLAttributes, ReactNode, Ref } from "react";

import { Breadcrumb, crumbLink } from "../design";
import { useAgent } from "../projects/agents";
import { useDocument } from "../projects/documents";
import { useProject } from "../projects/projects";
import { AGENT, ORGANISATION, PROJECT, useProjectSections } from "./projectNavigation";
import { SETTINGS, useSettingsAreas } from "./settingsNavigation";

/**
 * One crumb: a link whose `current` alone decides `aria-current="page"`, replacing the router's
 * own marking. The router marks every link to the page the Member is on, which would make the
 * Project's crumb current on its Documents page as well as the Documents crumb.
 */
function CrumbAnchor({ current = false, ref, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { current?: boolean; ref?: Ref<HTMLAnchorElement> }) {
  return <a ref={ref} {...props} aria-current={current ? "page" : undefined} className={crumbLink} />;
}

const Crumb = createLink(CrumbAnchor);

/** A Document's crumb, after Documents: its name, or "Document" until it loads or when it can't be. */
function DocumentCrumb({ organisationId, projectId, documentId }: { organisationId: string; projectId: string; documentId: string }) {
  const document = useDocument(organisationId, projectId, documentId);
  return (
    <Crumb to={`${PROJECT}/documents/$documentId`} params={{ organisationId, projectId, documentId }} current>
      {document.data?.name ?? "Document"}
    </Crumb>
  );
}

/**
 * Inside an Agent: the crumbs before it, then the Agent, current on every one of its views (the
 * tab row says which). Until the Agent has loaded, or when it can't be found, the crumbs end at
 * its section, which is then current.
 */
function AgentPath({
  organisationId,
  projectId,
  agentId,
  before,
}: {
  organisationId: string;
  projectId: string;
  agentId: string;
  before: (sectionCurrent: boolean) => ReactNode[];
}) {
  const agent = useAgent(organisationId, projectId, agentId);
  if (!agent.data) return <Breadcrumb>{before(true)}</Breadcrumb>;
  return (
    <Breadcrumb>
      {before(false)}
      <Crumb to={AGENT} params={{ organisationId, projectId, agentId }} current>
        {agent.data.name}
      </Crumb>
    </Breadcrumb>
  );
}

/** Where the Member is inside a Project: the Project, its section, then a Document or an Agent. */
function ProjectPath({ organisationId, projectId }: { organisationId: string; projectId: string }) {
  const matchRoute = useMatchRoute();
  const project = useProject(organisationId, projectId);
  const sections = useProjectSections(organisationId, projectId);

  // While the Project can't be shown (loading, not found) it is the only crumb.
  if (!project.data) {
    return (
      <Breadcrumb>
        <Crumb to={PROJECT} params={{ organisationId, projectId }} current>
          Project
        </Crumb>
      </Breadcrumb>
    );
  }
  // Every page in a Project belongs to one section.
  const section = sections.find((candidate) => candidate.current) as (typeof sections)[number];
  const before = (sectionCurrent: boolean) => [
    <Crumb key="project" to={PROJECT} params={{ organisationId, projectId }}>
      {project.data.name}
    </Crumb>,
    <Crumb key="section" to={section.to} params={{ organisationId, projectId }} current={sectionCurrent}>
      {section.label}
    </Crumb>,
  ];
  const agent = matchRoute({ to: AGENT, params: { organisationId, projectId }, fuzzy: true });
  if (agent !== false) {
    return <AgentPath organisationId={organisationId} projectId={projectId} agentId={agent.agentId} before={before} />;
  }
  const viewing = matchRoute({ to: `${PROJECT}/documents/$documentId`, params: { organisationId, projectId } });
  return (
    <Breadcrumb>
      {before(viewing === false)}
      {viewing !== false && <DocumentCrumb organisationId={organisationId} projectId={projectId} documentId={viewing.documentId} />}
    </Breadcrumb>
  );
}

/** Organisation settings: Settings, then the area the Member is in (none on an address that is no area). */
function SettingsPath({ organisationId }: { organisationId: string }) {
  const area = useSettingsAreas(organisationId).find((candidate) => candidate.current);
  return (
    <Breadcrumb>
      <Crumb to={SETTINGS} params={{ organisationId }}>
        Settings
      </Crumb>
      {area && (
        <Crumb to={area.to} params={{ organisationId }} current>
          {area.label}
        </Crumb>
      )}
    </Breadcrumb>
  );
}

type OrganisationPage =
  | "/organisations/$organisationId/projects"
  | "/organisations/$organisationId/cost"
  | "/organisations/$organisationId/security"
  | "/organisations/$organisationId/profile";

/** The Organisation's own pages outside settings, each a crumb of its own. */
const PAGES: { label: string; to: OrganisationPage }[] = [
  { label: "Projects", to: `${ORGANISATION}/projects` },
  { label: "Cost", to: `${ORGANISATION}/cost` },
  { label: "Security", to: `${ORGANISATION}/security` },
  { label: "Profile", to: `${ORGANISATION}/profile` },
];

/**
 * The top bar's breadcrumb, computed from the route (pages register nothing): plain links from the
 * Organisation's page the Member is under down to the page they are on, which is marked
 * `aria-current="page"`. The Organisation itself is named at the top of the sidebar.
 */
export function StudioBreadcrumb({ organisationId }: { organisationId: string }) {
  const matchRoute = useMatchRoute();
  const project = matchRoute({ to: PROJECT, params: { organisationId }, fuzzy: true });
  if (project !== false) return <ProjectPath organisationId={organisationId} projectId={project.projectId} />;
  if (matchRoute({ to: SETTINGS, params: { organisationId }, fuzzy: true }) !== false) {
    return <SettingsPath organisationId={organisationId} />;
  }
  const page = PAGES.find((candidate) => matchRoute({ to: candidate.to, params: { organisationId } }) !== false);
  return (
    <Breadcrumb>
      {page && (
        <Crumb to={page.to} params={{ organisationId }} current>
          {page.label}
        </Crumb>
      )}
    </Breadcrumb>
  );
}
