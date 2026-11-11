import { Link, useMatchRoute } from "@tanstack/react-router";

import type { IconName, MenuItem, MenuLinkProps } from "../design";
import { useAgents } from "../projects/agents";
import { useProjects } from "../projects/projects";

export const ORGANISATION = "/organisations/$organisationId";
export const PROJECT = "/organisations/$organisationId/projects/$projectId";

export type ProjectPath =
  | "/organisations/$organisationId/projects/$projectId"
  | "/organisations/$organisationId/projects/$projectId/documents/$documentId"
  | "/organisations/$organisationId/projects/$projectId/instructions"
  | "/organisations/$organisationId/projects/$projectId/agents"
  | "/organisations/$organisationId/projects/$projectId/conversations"
  | "/organisations/$organisationId/projects/$projectId/analytics"
  | "/organisations/$organisationId/projects/$projectId/settings";

/**
 * A Project's sections, in order. Documents is the Project's index page, so it is matched
 * exactly, and also holds the Document viewer; the others hold their inner pages (an Agent is
 * under Agents, a Conversation under Conversations).
 */
export const PROJECT_SECTIONS: { label: string; icon: IconName; to: ProjectPath; also?: ProjectPath }[] = [
  { label: "Documents", icon: "documents", to: PROJECT, also: `${PROJECT}/documents/$documentId` },
  { label: "Instructions", icon: "instructions", to: `${PROJECT}/instructions` },
  { label: "Agents", icon: "agents", to: `${PROJECT}/agents` },
  { label: "Conversations", icon: "conversations", to: `${PROJECT}/conversations` },
  { label: "Analytics", icon: "analytics", to: `${PROJECT}/analytics` },
  { label: "Settings", icon: "settings", to: `${PROJECT}/settings` },
];

/** A Project's sections, each with whether the Member is in it now. Every page in a Project belongs to one. */
export function useProjectSections(organisationId: string, projectId: string) {
  const matchRoute = useMatchRoute();
  return PROJECT_SECTIONS.map((section) => ({
    ...section,
    current:
      section.also === undefined
        ? matchRoute({ to: section.to, params: { organisationId, projectId }, fuzzy: true }) !== false
        : matchRoute({ to: section.to, params: { organisationId, projectId } }) !== false ||
          matchRoute({ to: section.also, params: { organisationId, projectId } }) !== false,
  }));
}

/** The Project switcher's menu: the Organisation's open Projects, the open one marked, then All Projects. */
export function useProjectSwitcherItems(organisationId: string, projectId: string): MenuItem[] {
  const projects = useProjects(organisationId, false);
  return [
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
}

export const AGENT = `${PROJECT}/agents/$agentId` as const;

type AgentViewPath = typeof AGENT | `${typeof AGENT}/versions` | `${typeof AGENT}/embed` | `${typeof AGENT}/conversations`;

/**
 * An Agent's views, in order: the tabs under its header.
 * Conversations also holds the Conversation opened from it.
 */
export const AGENT_VIEWS: { label: string; to: AgentViewPath; fuzzy?: boolean }[] = [
  { label: "Playground", to: AGENT },
  { label: "Versions", to: `${AGENT}/versions` },
  { label: "Embed & limits", to: `${AGENT}/embed` },
  { label: "Conversations", to: `${AGENT}/conversations`, fuzzy: true },
];

/** An Agent's views, each with whether the Member is in it now. Every page inside an Agent is one of them. */
export function useAgentViews(organisationId: string, projectId: string, agentId: string) {
  const matchRoute = useMatchRoute();
  return AGENT_VIEWS.map(({ fuzzy = false, ...view }) => ({
    ...view,
    current: matchRoute({ to: view.to, params: { organisationId, projectId, agentId }, fuzzy }) !== false,
  }));
}

/** The Agent switcher's menu: the Project's open Agents, the open one marked; each opens its Playground. */
export function useAgentSwitcherItems(organisationId: string, projectId: string, agentId: string): MenuItem[] {
  const agents = useAgents(organisationId, projectId);
  return (agents.data ?? []).map((candidate) => ({
    id: candidate.id,
    label: candidate.name,
    icon: "agents" as const,
    current: candidate.id === agentId,
    renderLink: (props: MenuLinkProps) => <Link to={AGENT} params={{ organisationId, projectId, agentId: candidate.id }} {...props} />,
  }));
}
