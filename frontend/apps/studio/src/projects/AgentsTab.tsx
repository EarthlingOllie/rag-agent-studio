import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { type SubmitEvent } from "react";

import { FormError, formValues } from "../auth/AuthLayout";
import { agentFailure, useAgents, useCreateAgent } from "./agents";
import { useProject } from "./projects";
import { BUTTON, INPUT, useOrganisationRole } from "./ProjectsPage";

function NewAgentForm({ organisationId, projectId }: { organisationId: string; projectId: string }) {
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
    <form aria-labelledby="new-agent-heading" onSubmit={onSubmit} className="max-w-md space-y-3">
      <h3 id="new-agent-heading" className="font-semibold">
        New Agent
      </h3>
      <FormError message={agentFailure(create.error)} />
      <div>
        <label htmlFor="new-agent-name" className="block text-sm font-medium">
          Name
        </label>
        <input id="new-agent-name" name="name" required maxLength={200} className={INPUT} />
      </div>
      <button type="submit" disabled={create.isPending} className={BUTTON}>
        {create.isPending ? "Creating…" : "Create Agent"}
      </button>
    </form>
  );
}

/** The Project's Agents, with a form to create one. */
export function AgentsTab() {
  const { organisationId } = useOrganisationRole();
  const { projectId } = useParams({ from: "/signed-in/organisations/$organisationId/projects/$projectId" });
  const project = useProject(organisationId, projectId);
  const agents = useAgents(organisationId, projectId);
  const archived = project.data?.archived_at != null;

  let list;
  if (agents.isPending) {
    list = <p role="status">Loading Agents…</p>;
  } else if (agents.isError) {
    list = <p role="alert">The Agents could not be loaded. Try again shortly.</p>;
  } else if (agents.data.length === 0) {
    list = <p className="text-slate-700">No Agents yet. Create one to answer questions from this Project's Documents.</p>;
  } else {
    list = (
      <ul className="divide-y divide-slate-200 rounded border border-slate-200 bg-white">
        {agents.data.map((agent) => (
          <li key={agent.id} className="px-4 py-3">
            <Link
              to="/organisations/$organisationId/projects/$projectId/agents/$agentId"
              params={{ organisationId, projectId, agentId: agent.id }}
              className="font-medium underline"
            >
              {agent.name}
            </Link>
          </li>
        ))}
      </ul>
    );
  }

  return (
    <section aria-labelledby="tab-heading" className="space-y-4">
      <h2 id="tab-heading" className="text-lg font-semibold">
        Agents
      </h2>
      {list}
      {!archived && <NewAgentForm organisationId={organisationId} projectId={projectId} />}
    </section>
  );
}
