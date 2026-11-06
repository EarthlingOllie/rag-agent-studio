import { Link, useNavigate, useParams, useSearch } from "@tanstack/react-router";
import { type SubmitEvent, useState } from "react";

import { FormError, formValues } from "../auth/AuthLayout";
import { agentFailure, useAgents, useCreateAgent } from "./agents";
import { useProject } from "./projects";
import { BUTTON, INPUT, useOrganisationRole } from "./ProjectsPage";

function NewAgentForm({
  organisationId,
  projectId,
}: {
  organisationId: string;
  projectId: string;
}) {
  const create = useCreateAgent(organisationId, projectId);
  const navigate = useNavigate();

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    create.mutate(formValues(event.currentTarget, ["name"]).name, {
      onSuccess: (agent) => {
        void navigate({
          to: "/organisations/$organisationId/projects/$projectId/agents/$agentId",
          params: { organisationId, projectId, agentId: agent.id },
        });
      },
    });
  }

  return (
    <form
      aria-labelledby="new-agent-heading"
      onSubmit={onSubmit}
      className="max-w-md space-y-3"
    >
      <h3 id="new-agent-heading" className="font-semibold">
        New Agent
      </h3>
      <FormError message={agentFailure(create.error)} />
      <div>
        <label htmlFor="new-agent-name" className="block text-sm font-medium">
          Name
        </label>
        <input
          id="new-agent-name"
          name="name"
          required
          maxLength={200}
          className={INPUT}
        />
      </div>
      <button type="submit" disabled={create.isPending} className={BUTTON}>
        {create.isPending ? "Creating…" : "Create Agent"}
      </button>
    </form>
  );
}

/** The Project's active Agents, or its archived ones, each linking to its page. */
function AgentList({
  organisationId,
  projectId,
  archived,
}: {
  organisationId: string;
  projectId: string;
  archived: boolean;
}) {
  const agents = useAgents(organisationId, projectId, archived);
  if (agents.isPending)
    return <p role="status">Loading Agents…</p>;
  if (agents.isError)
    return (
      <p role="alert">The Agents could not be loaded. Try again shortly.</p>
    );
  if (agents.data.length === 0)
    return archived ? (
      <p className="text-slate-700">No archived Agents.</p>
    ) : (
      <p className="text-slate-700">
        No Agents yet. Create one to answer questions from this Project's
        Documents.
      </p>
    );
  return (
    <ul
      aria-label={archived ? "Archived Agents" : "Agents"}
      className="divide-y divide-slate-200 rounded border border-slate-200 bg-white"
    >
      {agents.data.map((agent) => (
        <li key={agent.id} className="flex justify-between gap-4 px-4 py-3">
          <Link
            to="/organisations/$organisationId/projects/$projectId/agents/$agentId"
            params={{ organisationId, projectId, agentId: agent.id }}
            className="font-medium underline"
          >
            {agent.name}
          </Link>
          {agent.archived_at && (
            <span className="text-sm text-slate-700">
              Archived {agent.archived_at.slice(0, 10)}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

/** The Project's Agents, with a form to create one, and its archived Agents on request. */
export function AgentsTab() {
  const { organisationId, isOwner } = useOrganisationRole();
  const { projectId } = useParams({
    from: "/signed-in/organisations/$organisationId/projects/$projectId",
  });
  const { deleted } = useSearch({
    from: "/signed-in/organisations/$organisationId/projects/$projectId/agents",
  });
  const project = useProject(organisationId, projectId);
  const [showArchived, setShowArchived] = useState(false);
  const archivedProject = project.data?.archived_at != null;

  return (
    <section aria-labelledby="tab-heading" className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <h2 id="tab-heading" className="text-lg font-semibold">
          {showArchived ? "Archived Agents" : "Agents"}
        </h2>
        <button
          type="button"
          className={BUTTON}
          onClick={() => {
            setShowArchived(!showArchived);
          }}
        >
          {showArchived ? "Show active Agents" : "Show archived Agents"}
        </button>
      </div>
      {deleted && (
        <p role="status" className="text-sm text-green-900">
          {deleted} was deleted permanently.
        </p>
      )}
      {showArchived && (
        <p className="text-sm text-slate-700">
          Archived Agents are hidden from this list and the Playground, but
          keep their Draft and Conversations.{" "}
          {isOwner
            ? "Open one to restore it or delete it permanently."
            : "Only Owners can restore or delete them."}
        </p>
      )}
      <AgentList
        key={String(showArchived)}
        organisationId={organisationId}
        projectId={projectId}
        archived={showArchived}
      />
      {!archivedProject && !showArchived && (
        <NewAgentForm organisationId={organisationId} projectId={projectId} />
      )}
    </section>
  );
}
