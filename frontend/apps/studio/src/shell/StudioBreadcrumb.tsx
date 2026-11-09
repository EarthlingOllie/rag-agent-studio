import { Link, useMatchRoute } from "@tanstack/react-router";

import type { Session } from "../auth/session";
import { Breadcrumb, CrumbSwitcher, CrumbText, type IconName, type MenuItem } from "../design";
import { useProject } from "../projects/projects";
import { OrganisationCrumb } from "./OrganisationSwitcher";

const ORGANISATION = "/organisations/$organisationId";
const PROJECT = "/organisations/$organisationId/projects/$projectId";

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

function ProjectCrumb({ organisationId, projectId }: { organisationId: string; projectId: string }) {
  const project = useProject(organisationId, projectId);
  return <CrumbText current>{project.data?.name ?? "Project"}</CrumbText>;
}

/**
 * The top bar's breadcrumb, computed from the route: Organisation / section, then the Project
 * when one is open. Pages register nothing. While the Organisation requires MFA and
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

  return (
    <Breadcrumb>
      <OrganisationCrumb session={session} organisationId={organisationId} />
      {organisation && here && (
        <CrumbSwitcher label={here.label} menuLabel="Organisation sections" items={sections} current={project === false} />
      )}
      {organisation && project !== false && <ProjectCrumb organisationId={organisationId} projectId={project.projectId} />}
      {organisation && !here && costElsewhere && <CrumbText current>Cost</CrumbText>}
    </Breadcrumb>
  );
}
