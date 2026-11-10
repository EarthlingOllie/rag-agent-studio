import { Link, useMatchRoute } from "@tanstack/react-router";
import type { ReactNode } from "react";

import type { Session } from "../auth/session";
import { Breadcrumb, CrumbSwitcher, CrumbText, type IconName, type MenuItem, type MenuLinkProps } from "../design";
import { useAgent } from "../projects/agents";
import { useDocument } from "../projects/documents";
import { useProject } from "../projects/projects";
import { OrganisationCrumb } from "./OrganisationSwitcher";
import {
  AGENT,
  ORGANISATION,
  PROJECT,
  useAgentSwitcherItems,
  useAgentViews,
  useProjectSections,
  useProjectSwitcherItems,
} from "./projectNavigation";
import { SettingsCrumb } from "./SettingsCrumb";

const SETTINGS = "/organisations/$organisationId/settings";

type SectionPath =
  | "/organisations/$organisationId/projects"
  | "/organisations/$organisationId/cost"
  | "/organisations/$organisationId/settings"
  | "/organisations/$organisationId/security"
  | "/organisations/$organisationId/profile";

/**
 * The Organisation's sections, in menu order. Cost is for Owners, as the side menu had it. Profile
 * is the Member's own page; it is also in the account menu.
 */
const SECTIONS: { label: string; icon: IconName; to: SectionPath; ownersOnly?: true }[] = [
  { label: "Projects", icon: "projects", to: "/organisations/$organisationId/projects" },
  { label: "Cost", icon: "analytics", to: "/organisations/$organisationId/cost", ownersOnly: true },
  { label: "Settings", icon: "settings", to: "/organisations/$organisationId/settings" },
  { label: "Security", icon: "security", to: "/organisations/$organisationId/security" },
  { label: "Profile", icon: "profile", to: "/organisations/$organisationId/profile" },
];

/**
 * Inside an Agent: the crumbs `before` it, its section crumb (`section`), the Agent crumb, a
 * switcher of the Project's open Agents, then the view switcher (Playground, Versions, Embed &
 * limits, Conversations). Until the Agent is loaded, or when it can't be found, the section crumb
 * is the current one.
 */
function AgentBreadcrumb({
  organisationId,
  projectId,
  agentId,
  before,
  section,
}: {
  organisationId: string;
  projectId: string;
  agentId: string;
  before: ReactNode[];
  section: (current: boolean) => ReactNode;
}) {
  const switcher = useAgentSwitcherItems(organisationId, projectId, agentId);
  const views: MenuItem[] = useAgentViews(organisationId, projectId, agentId).map(({ label, icon, to, current }) => ({
    label,
    icon,
    current,
    renderLink: (props: MenuLinkProps) => <Link to={to} params={{ organisationId, projectId, agentId }} {...props} />,
  }));
  const agent = useAgent(organisationId, projectId, agentId);
  if (!agent.data) {
    return (
      <Breadcrumb>
        {before}
        {section(true)}
      </Breadcrumb>
    );
  }
  // Every view inside the Agent's route is one of its views.
  const here = views.find((view) => view.current) as MenuItem;
  return (
    <Breadcrumb>
      {before}
      {section(false)}
      <CrumbSwitcher label={agent.data.name} menuLabel="Agents" items={switcher} />
      <CrumbSwitcher label={here.label} menuLabel="Agent views" items={views} current />
    </Breadcrumb>
  );
}

/** A Document's own crumb, after the Documents switcher: its name, or "Document" until it loads. */
function DocumentCrumb({ organisationId, projectId, documentId }: { organisationId: string; projectId: string; documentId: string }) {
  const document = useDocument(organisationId, projectId, documentId);
  return <CrumbText current>{document.data?.name ?? "Document"}</CrumbText>;
}

/**
 * The Project crumb, a switcher of the Organisation's open Projects plus All Projects, then the
 * Project's section switcher, then on the Document viewer the Document's name. While the Project
 * can't be shown (loading, not found) there are no sections, and the Project crumb is the current one.
 */
function ProjectBreadcrumb({
  organisationId,
  projectId,
  leading,
}: {
  organisationId: string;
  projectId: string;
  /** The Organisation's crumbs, before the Project's. */
  leading: ReactNode[];
}) {
  const matchRoute = useMatchRoute();
  const project = useProject(organisationId, projectId);

  const switcher = useProjectSwitcherItems(organisationId, projectId);
  // The number hints are a visual label only, hidden from assistive technology.
  const sections: MenuItem[] = useProjectSections(organisationId, projectId).map((section, index) => ({
    label: section.label,
    icon: section.icon,
    hint: String(index + 1),
    current: section.current,
    renderLink: (props) => <Link to={section.to} params={{ organisationId, projectId }} {...props} />,
  }));
  // Every page in a Project belongs to one section.
  const here = sections.find((section) => section.current) as MenuItem;
  const agent = matchRoute({ to: AGENT, params: { organisationId, projectId }, fuzzy: true });
  const sectionCrumb = (current: boolean) => (
    <CrumbSwitcher key="section" label={here.label} menuLabel="Project sections" items={sections} current={current} />
  );
  const viewing = matchRoute({ to: `${PROJECT}/documents/$documentId`, params: { organisationId, projectId } });

  const projectCrumb = (
    <CrumbSwitcher key="project" label={project.data?.name ?? "Project"} menuLabel="Projects" items={switcher} current={!project.data} />
  );

  if (project.data && agent !== false) {
    return (
      <AgentBreadcrumb
        organisationId={organisationId}
        projectId={projectId}
        agentId={agent.agentId}
        before={[...leading, projectCrumb]}
        section={sectionCrumb}
      />
    );
  }
  return (
    <Breadcrumb>
      {leading}
      {projectCrumb}
      {project.data && sectionCrumb(viewing === false)}
      {project.data && viewing !== false && (
        <DocumentCrumb organisationId={organisationId} projectId={projectId} documentId={viewing.documentId} />
      )}
    </Breadcrumb>
  );
}

/**
 * The top bar's breadcrumb, computed from the route: Organisation / section, then the Project and
 * its section when one is open, or the settings area (`SettingsCrumb`). Pages register nothing.
 * While the Organisation requires MFA and the Member has none, the section switcher offers only
 * Security.
 */
export function StudioBreadcrumb({
  session,
  organisationId,
  mustEnrol,
}: {
  session: Session;
  organisationId: string;
  mustEnrol: boolean;
}) {
  const matchRoute = useMatchRoute();
  const organisation = session.organisations.find((candidate) => candidate.id === organisationId);
  const project = matchRoute({ to: PROJECT, params: { organisationId }, fuzzy: true });
  const settings = matchRoute({ to: SETTINGS, params: { organisationId }, fuzzy: true }) !== false;
  // The one page outside the section menu: Cost, for a Member who isn't an Owner.
  const costElsewhere = matchRoute({ to: `${ORGANISATION}/cost`, params: { organisationId } }) !== false;

  const sections: MenuItem[] = SECTIONS.filter(
    (section) => (!mustEnrol || section.label === "Security") && (section.ownersOnly !== true || organisation?.role === "owner"),
  ).map((section) => ({
    label: section.label,
    icon: section.icon,
    current: matchRoute({ to: section.to, params: { organisationId }, fuzzy: true }) !== false,
    renderLink: (props) => <Link to={section.to} params={{ organisationId }} {...props} />,
  }));
  const here = sections.find((section) => section.current);
  const leading = [
    <OrganisationCrumb key="organisation" session={session} organisationId={organisationId} />,
    organisation && here && (
      <CrumbSwitcher key="sections" label={here.label} menuLabel="Organisation sections" items={sections} current={project === false && !settings} />
    ),
  ];

  if (organisation && project !== false) {
    return <ProjectBreadcrumb organisationId={organisationId} projectId={project.projectId} leading={leading} />;
  }
  return (
    <Breadcrumb>
      {leading}
      {organisation && settings && <SettingsCrumb organisationId={organisationId} isOwner={organisation.role === "owner"} />}
      {organisation && !here && costElsewhere && <CrumbText current>Cost</CrumbText>}
    </Breadcrumb>
  );
}
