import { Link, useNavigate, useParams, useSearch } from "@tanstack/react-router";
import { type SubmitEvent, useState } from "react";

import { FormError, formValues } from "../auth/AuthLayout";
import {
  Badge,
  BulkBar,
  button,
  ConfirmDialog,
  Dialog,
  EmptyState,
  field,
  layout,
  Notice,
  PageHeader,
  Segmented,
  Skeleton,
  surface,
  table,
} from "../design";
import { type Agent, agentFailure, useAgents, useCreateAgent } from "./agents";
import { bulkFailure, useBulkRevert } from "./bulk";
import { BulkResults } from "./BulkRollout";
import { useProject } from "./projects";
import { useOrganisationRole } from "./ProjectsPage";

type Shown = "active" | "archived";

const SHOWN_OPTIONS = [
  { value: "active", label: "Active" },
  { value: "archived", label: "Archived" },
] as const;

const BUDGET_SPENT = "Today's Token Budget is spent, so Visitors see the unavailable text until midnight UTC.";
const BLOCK_RATE_SPIKE =
  "Block rate spike: in the last hour, the input Guardrail blocked an unusual share of Visitor messages, as in an attack. Review the blocked Conversations.";
const DRAFT_CHANGES = "Unpublished changes: the Draft differs from the Live Version.";

const agentCount = (count: number) => `${String(count)} ${count === 1 ? "Agent" : "Agents"}`;

/** The New Agent dialog: a name, then the new Agent's page opens. */
function NewAgentDialog({ organisationId, projectId, onClose }: { organisationId: string; projectId: string; onClose: () => void }) {
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
    <Dialog open title="New Agent" onClose={onClose} closeButton={false}>
      <form aria-label="New Agent" onSubmit={onSubmit} className="flex flex-col gap-4">
        <div>
          <label htmlFor="new-agent-name" className={field.label}>
            Name
          </label>
          <input id="new-agent-name" name="name" required maxLength={200} className={field.input} />
        </div>
        <FormError message={agentFailure(create.error)} />
        <div className="flex flex-wrap justify-end gap-2 pt-2">
          <button type="button" className={button.secondary} onClick={onClose}>
            Cancel
          </button>
          <button type="submit" disabled={create.isPending} className={button.primary}>
            {create.isPending ? "Creating…" : "Create Agent"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}

/** Live v<N> or Not live. */
function LiveCell({ agent }: { agent: Agent }) {
  if (!agent.live_version) return <Badge kind="notLive" />;
  return (
    <span className="inline-flex items-center gap-1.5">
      <Badge kind="live" />{" "}
      <Badge kind="version" version={agent.live_version.number} />
    </span>
  );
}

/** The alerts an Agent needs looked at: a spent Token Budget, a spike in Guardrail blocks. */
function AlertsCell({ agent }: { agent: Agent }) {
  if (!agent.budget_exhausted && !agent.block_rate_alert) return <span className="text-muted">—</span>;
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      {agent.budget_exhausted && <Badge kind="budgetSpent" title={BUDGET_SPENT} />}
      {agent.block_rate_alert && <Badge kind="blocked" title={BLOCK_RATE_SPIKE} />}
    </span>
  );
}

/** One table of Agents. With `selection`, each row and the header have a checkbox. */
function AgentTable({
  agents,
  archived,
  organisationId,
  projectId,
  selection,
}: {
  agents: Agent[];
  archived: boolean;
  organisationId: string;
  projectId: string;
  selection?: { selected: string[]; onChange: (selected: string[]) => void } | undefined;
}) {
  const all = selection !== undefined && agents.every((agent) => selection.selected.includes(agent.id));
  const some = selection !== undefined && selection.selected.length > 0;
  return (
    <div className={table.wrap}>
      <table aria-label={archived ? "Archived Agents" : "Agents"} className={table.table}>
        <thead>
          <tr>
            {selection && (
              <th scope="col" className={`${table.th} w-10`}>
                <input
                  type="checkbox"
                  aria-label="Select all Agents"
                  checked={all}
                  ref={(input) => {
                    if (input) input.indeterminate = some && !all;
                  }}
                  onChange={() => {
                    selection.onChange(all ? [] : agents.map((agent) => agent.id));
                  }}
                />
              </th>
            )}
            <th scope="col" className={table.th}>
              Name
            </th>
            <th scope="col" className={table.th}>
              Live
            </th>
            <th scope="col" className={table.th}>
              Draft
            </th>
            <th scope="col" className={table.th}>
              Alerts
            </th>
            <th scope="col" className={table.th}>
              {archived ? "Archived" : "Draft saved"}
            </th>
          </tr>
        </thead>
        <tbody>
          {agents.map((agent) => (
            <tr key={agent.id} className={table.row}>
              {selection && (
                <td className={table.td}>
                  <input
                    type="checkbox"
                    aria-label={`Select ${agent.name}`}
                    checked={selection.selected.includes(agent.id)}
                    onChange={(event) => {
                      selection.onChange(
                        event.currentTarget.checked
                          ? [...selection.selected, agent.id]
                          : selection.selected.filter((id) => id !== agent.id),
                      );
                    }}
                  />
                </td>
              )}
              <td className={table.td}>
                <Link
                  to="/organisations/$organisationId/projects/$projectId/agents/$agentId"
                  params={{ organisationId, projectId, agentId: agent.id }}
                  className={table.link}
                >
                  {agent.name}
                </Link>
              </td>
              <td className={table.td}>
                <LiveCell agent={agent} />
              </td>
              <td className={table.td}>
                {agent.has_unpublished_changes ? <Badge kind="draft" title={DRAFT_CHANGES} /> : <span className="text-muted">—</span>}
              </td>
              <td className={table.td}>
                <AlertsCell agent={agent} />
              </td>
              <td className={`${table.tdMuted} font-mono text-[13px]`}>
                {(archived ? (agent.archived_at as string) : agent.draft_updated_at).slice(0, 10)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * The Project's active Agents, or its archived ones. Active Agents of an active Project can be
 * selected; the bulk bar then reverts them together, after confirmation, and reports each one.
 */
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
  const revert = useBulkRevert(organisationId, projectId);
  const [selected, setSelected] = useState<string[]>([]);
  const [confirming, setConfirming] = useState(false);

  if (agents.isPending) return <Skeleton label="Loading Agents" />;
  if (agents.isError) return <EmptyState tone="error" title="The Agents could not be loaded" description="Try again shortly." />;
  if (agents.data.length === 0)
    return archived ? (
      <EmptyState icon="agents" title="No archived Agents" description="An Agent you archive is kept here, with its Draft and Conversations." />
    ) : (
      <EmptyState icon="agents" title="No Agents yet" description="Create one with New Agent to answer questions from this Project's Documents." />
    );

  const count = agentCount(selected.length);
  return (
    <div className="flex flex-col gap-4">
      {selectable && (
        <BulkBar
          count={selected.length}
          noun={["Agent", "Agents"]}
          onClear={() => {
            setSelected([]);
          }}
        >
          <button
            type="button"
            className={button.secondary}
            onClick={() => {
              revert.reset();
              setConfirming(true);
            }}
          >
            Revert
          </button>
        </BulkBar>
      )}
      <FormError message={bulkFailure(revert.error)} />
      {revert.isSuccess && (
        <div className={surface.panel}>
          <BulkResults result={revert.data} verb="Reverted to" />
        </div>
      )}
      <AgentTable
        agents={agents.data}
        archived={archived}
        organisationId={organisationId}
        projectId={projectId}
        selection={selectable ? { selected, onChange: setSelected } : undefined}
      />
      <ConfirmDialog
        open={confirming}
        destructive
        title={`Revert ${count}?`}
        confirmLabel={`Yes, revert ${count}`}
        busy={revert.isPending}
        onCancel={() => {
          setConfirming(false);
        }}
        onConfirm={() => {
          revert.mutate(selected, {
            onSuccess: () => {
              setSelected([]);
            },
            onSettled: () => {
              setConfirming(false);
            },
          });
        }}
      >
        Each one's Live Version moves back one step in its Live History. Drafts aren't changed.
      </ConfirmDialog>
    </div>
  );
}

/**
 * The Project's Agents section: a page header with New Agent (the one primary), a filter for
 * archived Agents, and the Agents table with its bulk bar.
 */
export function AgentsTab() {
  const { organisationId, isOwner } = useOrganisationRole();
  const { projectId } = useParams({
    from: "/signed-in/organisations/$organisationId/projects/$projectId",
  });
  const { deleted } = useSearch({
    from: "/signed-in/organisations/$organisationId/projects/$projectId/agents",
  });
  const project = useProject(organisationId, projectId);
  const [shown, setShown] = useState<Shown>("active");
  const [creating, setCreating] = useState(false);
  const archivedProject = project.data?.archived_at != null;
  const archived = shown === "archived";

  return (
    <section aria-label="Agents" className={layout.stack}>
      <PageHeader
        level={2}
        title="Agents"
        description="Each Agent answers from this Project's Documents."
        actions={
          !archivedProject && (
            <button
              type="button"
              className={button.primary}
              onClick={() => {
                setCreating(true);
              }}
            >
              New Agent
            </button>
          )
        }
      />
      {deleted && <Notice tone="success">{deleted} was deleted permanently.</Notice>}
      <div className={layout.toolbar}>
        <Segmented label="Agents shown" options={SHOWN_OPTIONS} value={shown} onChange={setShown} />
      </div>
      {archived && (
        <p className="text-sm text-muted">
          Archived Agents are hidden from this list and the Playground, but keep their Draft and Conversations.{" "}
          {isOwner ? "Open one to restore it or delete it permanently." : "Only Owners can restore or delete them."}
        </p>
      )}
      <AgentList
        key={shown}
        organisationId={organisationId}
        projectId={projectId}
        archived={archived}
        selectable={!archived && project.data?.archived_at === null}
      />
      {creating && (
        <NewAgentDialog
          organisationId={organisationId}
          projectId={projectId}
          onClose={() => {
            setCreating(false);
          }}
        />
      )}
    </section>
  );
}
