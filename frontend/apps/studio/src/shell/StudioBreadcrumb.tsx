import { Link, useMatchRoute } from "@tanstack/react-router";
import type { ReactNode } from "react";

import type { Session } from "../auth/session";
import { Breadcrumb, CrumbSwitcher, CrumbText, type IconName, type MenuItem, type MenuLinkProps } from "../design";
import { useProject, useProjects } from "../projects/projects";
import { OrganisationCrumb } from "./OrganisationSwitcher";

const ORGANISATION = "/organisations/$organisationId";
const PROJECT = "/organisations/$organisationId/projects/$projectId";

type SectionPath =
  | "/organisations/$organisationId/projects"
  | "/organisations/$organisationId/cost"
  | "/organisations/$organisationId/settings"
  | "/organisations/$organisationId/security";

/** The Organisation's sections, in menu order. Cost is for Owners, as the side menu had it. */
const SECTIONS: { label: string; icon: IconName; to: SectionPath; ownersOnly?: true }[] = [
  { label: "Projects", icon: "projects", to: "/organisations/$organisationId/projects" },
  { label: "Cost", icon: "analytics", to: "/organisations/$organisationId/cost", ownersOnly: true },
  { label: "Settings", icon: "settings", to: "/organisations/$organisationId/settings" },
  { label: "Security", icon: "security", to: "/organisations/$organisationId/security" },
];

type ProjectPath =
  | "/organisations/$organisationId/projects/$projectId"
  | "/organisations/$organisationId/projects/$projectId/documents/$documentId"
  | "/organisations/$organisationId/projects/$projectId/instructions"
  | "/organisations/$organisationId/projects/$projectId/agents"
  | "/organisations/$organisationId/projects/$projectId/conversations"
  | "/organisations/$organisationId/projects/$projectId/analytics"
  | "/organisations/$organisationId/projects/$projectId/settings";

/**
 * A Project's sections, in menu order, numbered 1-6. Documents is the Project's index page, so it
 * is matched exactly, and also holds the Document viewer; the others hold their inner pages.
 */
const PROJECT_SECTIONS: { label: string; icon: IconName; to: ProjectPath; also?: ProjectPath }[] = [
  { label: "Documents", icon: "documents", to: PROJECT, also: `${PROJECT}/documents/$documentId` },
  { label: "Instructions", icon: "instructions", to: `${PROJECT}/instructions` },
  { label: "Agents", icon: "agents", to: `${PROJECT}/agents` },
  { label: "Conversations", icon: "conversations", to: `${PROJECT}/conversations` },
  { label: "Analytics", icon: "analytics", to: `${PROJECT}/analytics` },
  { label: "Settings", icon: "settings", to: `${PROJECT}/settings` },
];

/**
 * The Project crumb, a switcher of the Organisation's open Projects plus All Projects, then the
 * Project's section switcher. While the Project can't be shown (loading, not found) there are no
 * sections, and the Project crumb is the current one.
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
  const projects = useProjects(organisationId, false);
  const project = useProject(organisationId, projectId);

  const switcher: MenuItem[] = [
    ...(projects.data ?? []).map((candidate) => ({
      id: candidate.id,
      label: candidate.name,
      icon: "projects" as const,
      current: candidate.id === projectId,
      renderLink: (props: MenuLinkProps) => <Link to={PROJECT} params={{ organisationId, projectId: candidate.id }} {...props} />,
    })),
    {
      label: "All Projects",
      renderLink: (props: MenuLinkProps) => <Link to={`${ORGANISATION}/projects`} params={{ organisationId }} {...props} />,
    },
  ];
  const sections: MenuItem[] = PROJECT_SECTIONS.map((section, index) => ({
    label: section.label,
    icon: section.icon,
    hint: String(index + 1),
    current:
      section.also === undefined
        ? matchRoute({ to: section.to, params: { organisationId, projectId }, fuzzy: true }) !== false
        : matchRoute({ to: section.to, params: { organisationId, projectId } }) !== false ||
          matchRoute({ to: section.also, params: { organisationId, projectId } }) !== false,
    renderLink: (props) => <Link to={section.to} params={{ organisationId, projectId }} {...props} />,
  }));
  // Every page in a Project belongs to one section.
  const here = sections.find((section) => section.current) as MenuItem;

  return (
    <Breadcrumb>
      {leading}
      <CrumbSwitcher label={project.data?.name ?? "Project"} menuLabel="Projects" items={switcher} current={!project.data} />
      {project.data && <CrumbSwitcher label={here.label} menuLabel="Project sections" items={sections} current />}
    </Breadcrumb>
  );
}

/**
 * The top bar's breadcrumb, computed from the route: Organisation / section, then the Project and
 * its section when one is open, or Profile. Pages register nothing. While the Organisation requires MFA and
 * the Member has none, the section switcher offers only Security.
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
  // Pages outside the section menu: the Profile, and Cost for a Member who isn't an Owner.
  const elsewhere = ["Profile", "Cost"].find(
    (label) => matchRoute({ to: `${ORGANISATION}/${label.toLowerCase() as "profile" | "cost"}`, params: { organisationId } }) !== false,
  );

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
      <CrumbSwitcher key="sections" label={here.label} menuLabel="Organisation sections" items={sections} current={project === false} />
    ),
  ];

  if (organisation && project !== false) {
    return <ProjectBreadcrumb organisationId={organisationId} projectId={project.projectId} leading={leading} />;
  }
  return (
    <Breadcrumb>
      {leading}
      {organisation && !here && elsewhere !== undefined && <CrumbText current>{elsewhere}</CrumbText>}
    </Breadcrumb>
  );
}
