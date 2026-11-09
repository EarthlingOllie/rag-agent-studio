import { Link, useNavigate, useParams, useSearch } from "@tanstack/react-router";
import { type SubmitEvent, useState } from "react";

import { FormError, formValues } from "../auth/AuthLayout";
import { LiveStatus } from "./AgentPublish";
import { agentFailure, useAgents, useCreateAgent } from "./agents";
import { bulkFailure, useBulkRevert } from "./bulk";
import { BulkResults } from "./BulkRollout";
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

/** Reverts the selected Agents together, after confirmation, and reports each one's result. */
function BulkRevert({
  organisationId,
  projectId,
  selected,
  onDone,
}: {
  organisationId: string;
  projectId: string;
  selected: string[];
  onDone: () => void;
}) {
  const revert = useBulkRevert(organisationId, projectId);
  const [confirming, setConfirming] = useState(false);
  const count = `${String(selected.length)} ${selected.length === 1 ? "Agent" : "Agents"}`;

  return (
    <div role="group" aria-label="Bulk actions" className="space-y-2">
      <FormError message={bulkFailure(revert.error)} />
      {confirming ? (
        <div className="flex flex-wrap items-center gap-2">
          <span>
            Revert {count}? Each one's Live Version moves back one step in its Live History. Drafts aren't changed.
          </span>
          <button
            type="button"
            disabled={revert.isPending}
            className="rounded bg-danger px-2 py-1 text-on-danger"
            onClick={() => {
              revert.mutate(selected, {
                onSuccess: onDone,
                onSettled: () => {
                  setConfirming(false);
                },
              });
            }}
          >
            Yes, revert {count}
          </button>
          <button
            type="button"
            className="underline"
            onClick={() => {
              setConfirming(false);
            }}
          >
            Cancel
          </button>
        </div>
      ) : (
        <button
          type="button"
          className={BUTTON}
          disabled={selected.length === 0}
          onClick={() => {
            revert.reset();
            setConfirming(true);
          }}
        >
          Revert selected ({selected.length})
        </button>
      )}
      {revert.isSuccess && <BulkResults result={revert.data} verb="Reverted to" />}
    </div>
  );
}

/** The Project's active Agents, or its archived ones, each linking to its page. Active Agents
 * of an active Project can be selected and reverted together. */
function AgentList({
  organisationId,
  projectId,
  archived,
  selectable,
}: {
  organisationId: string;
  projectId: string;
  archived: boolean;
  selectable: boolean;
}) {
  const agents = useAgents(organisationId, projectId, archived);
  const [selected, setSelected] = useState<string[]>([]);
  if (agents.isPending)
    return <p role="status">Loading Agents…</p>;
  if (agents.isError)
    return (
      <p role="alert">The Agents could not be loaded. Try again shortly.</p>
    );
  if (agents.data.length === 0)
    return archived ? (
      <p className="text-muted">No archived Agents.</p>
    ) : (
      <p className="text-muted">
        No Agents yet. Create one to answer questions from this Project's
        Documents.
      </p>
    );
  const list = (
    <ul
      aria-label={archived ? "Archived Agents" : "Agents"}
      className="divide-y divide-line rounded border border-line bg-surface"
    >
      {agents.data.map((agent) => (
        <li key={agent.id} className="flex justify-between gap-4 px-4 py-3">
          <span className="flex items-center gap-3">
            {selectable && (
              <input
                type="checkbox"
                aria-label={`Select ${agent.name}`}
                checked={selected.includes(agent.id)}
                onChange={(event) => {
                  setSelected(
                    event.currentTarget.checked
                      ? [...selected, agent.id]
                      : selected.filter((id) => id !== agent.id),
                  );
                }}
              />
            )}
            <Link
            to="/organisations/$organisationId/projects/$projectId/agents/$agentId"
            params={{ organisationId, projectId, agentId: agent.id }}
            className="font-medium underline"
          >
              {agent.name}
            </Link>
          </span>
          <span className="flex items-center gap-3">
            <LiveStatus agent={agent} />
            {agent.archived_at && (
              <span className="text-sm text-muted">
                Archived {agent.archived_at.slice(0, 10)}
              </span>
            )}
          </span>
        </li>
      ))}
    </ul>
  );
  if (!selectable) return list;
  return (
    <div className="space-y-3">
      <BulkRevert
        organisationId={organisationId}
        projectId={projectId}
        selected={selected}
        onDone={() => {
          setSelected([]);
        }}
      />
      {list}
    </div>
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
        <p role="status" className="text-sm text-accent-ink">
          {deleted} was deleted permanently.
        </p>
      )}
      {showArchived && (
        <p className="text-sm text-muted">
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
        selectable={!showArchived && project.data?.archived_at === null}
      />
      {!archivedProject && !showArchived && (
        <NewAgentForm organisationId={organisationId} projectId={projectId} />
      )}
    </section>
  );
}
