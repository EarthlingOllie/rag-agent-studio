import { Link, useMatchRoute } from "@tanstack/react-router";

import type { Session } from "../auth/session";
import {
  Icon,
  type IconName,
  Menu,
  Sidebar,
  SidebarDivider,
  SidebarGroup,
  SidebarLabel,
  sidebarLink,
  sidebarSwitcher,
} from "../design";
import { useProject } from "../projects/projects";
import { SidebarOrganisation } from "./OrganisationSwitcher";
import { ORGANISATION, PROJECT, useProjectSections, useProjectSwitcherItems } from "./projectNavigation";

type OrganisationPath =
  | "/organisations/$organisationId/projects"
  | "/organisations/$organisationId/cost"
  | "/organisations/$organisationId/settings"
  | "/organisations/$organisationId/security";

/**
 * The Organisation's links, in order. Projects and Cost are current on their own page only (inside
 * a Project, the Project's section is); Settings on every settings page. Security is offered only
 * under the Require MFA policy, until the Member enrols; otherwise it is in the account menu.
 */
const ORGANISATION_LINKS: { label: string; icon: IconName; to: OrganisationPath; fuzzy: boolean; ownersOnly?: true }[] = [
  { label: "Projects", icon: "projects", to: `${ORGANISATION}/projects`, fuzzy: false },
  { label: "Cost", icon: "analytics", to: `${ORGANISATION}/cost`, fuzzy: false, ownersOnly: true },
  { label: "Settings", icon: "settings", to: `${ORGANISATION}/settings`, fuzzy: true },
];
const SECURITY = { label: "Security", icon: "security", to: `${ORGANISATION}/security`, fuzzy: false } as const;

/**
 * Link props that leave "current" to us: the router marks a link `aria-current="page"` itself when
 * the address starts with its path, which would make Projects current inside every Project. With
 * `exact` it marks only the link's own page, which is always one we mark too.
 */
const OWN_CURRENT = { activeOptions: { exact: true, includeSearch: false } } as const;

function current(isCurrent: boolean) {
  return isCurrent ? "page" : undefined;
}

/** Inside a Project: its switcher, then its six sections once it has loaded. */
function ProjectNavigation({ organisationId, projectId }: { organisationId: string; projectId: string }) {
  const project = useProject(organisationId, projectId);
  const switcher = useProjectSwitcherItems(organisationId, projectId);
  const sections = useProjectSections(organisationId, projectId);
  const label = project.data?.name ?? "Project";
  return (
    <>
      <SidebarDivider />
      <Menu
        label={
          <>
            <span className="flex min-w-0 items-center gap-2.5">
              <Icon name="projects" className="shrink-0 text-muted" />
              <span className="truncate">{label}</span>
            </span>
            <Icon name="chevronDown" size={14} className="shrink-0 text-muted" />
          </>
        }
        triggerLabel={`${label}, Projects`}
        menuLabel="Projects"
        triggerClassName={sidebarSwitcher}
        wrapperClassName="relative mb-1 flex"
        items={switcher}
      />
      {project.data && (
        <SidebarGroup label="Project sections">
          {sections.map((section) => (
            <li key={section.label}>
              <Link
                to={section.to}
                params={{ organisationId, projectId }}
                {...OWN_CURRENT}
                aria-current={current(section.current)}
                className={sidebarLink}
              >
                <SidebarLabel icon={section.icon}>{section.label}</SidebarLabel>
              </Link>
            </li>
          ))}
        </SidebarGroup>
      )}
    </>
  );
}

/**
 * The sidebar, computed from the route and the Member's session (pages register nothing): the
 * Organisation switcher, the Organisation's links, and inside a Project the Project switcher and
 * its sections. Under the Require MFA policy, until the Member enrols, it offers only Security.
 */
export function StudioSidebar({
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
  const links = mustEnrol
    ? [SECURITY]
    : ORGANISATION_LINKS.filter((link) => link.ownersOnly !== true || organisation?.role === "owner");

  return (
    <Sidebar label="Studio">
      <SidebarOrganisation session={session} organisationId={organisationId} />
      {organisation && (
        <SidebarGroup label="Organisation sections">
          {links.map((link) => (
            <li key={link.label}>
              <Link
                to={link.to}
                params={{ organisationId }}
                {...OWN_CURRENT}
                aria-current={current(matchRoute({ to: link.to, params: { organisationId }, fuzzy: link.fuzzy }) !== false)}
                className={sidebarLink}
              >
                <SidebarLabel icon={link.icon}>{link.label}</SidebarLabel>
              </Link>
            </li>
          ))}
        </SidebarGroup>
      )}
      {organisation && !mustEnrol && project !== false && (
        <ProjectNavigation organisationId={organisationId} projectId={project.projectId} />
      )}
    </Sidebar>
  );
}
