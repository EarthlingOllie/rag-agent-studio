import { Notice, Status, button, text } from "../design";
import {
  type EvaluationRun,
  type RolloutAgentEvaluation,
  type RolloutEvaluation,
  evaluationFailure,
  useRolloutEvaluation,
  useStartRolloutEvaluation,
} from "./evaluation";
import { RegressionList } from "./PublishEvaluation";

const regressions = (count: number) =>
  `${String(count)} ${count === 1 ? "Regression" : "Regressions"}`;

/** One Agent's Rollout evaluation: Regressions (each with why it failed), running, clear or not evaluated. */
export function AgentRolloutEvaluation({
  evaluation,
}: {
  evaluation: RolloutAgentEvaluation | undefined;
}) {
  if (evaluation === undefined) return null;
  switch (evaluation.state) {
    case "not_evaluated":
      return (
        <span className={text.small}>
          {evaluation.has_set
            ? "Not evaluated"
            : "Not evaluated: no Evaluation Set"}
        </span>
      );
    case "running": {
      // A running Agent always has its Rollout evaluation.
      const { progress } = evaluation.run as EvaluationRun;
      return (
        <Status tone="working">
          {`Evaluating, ${String(progress.done)} of ${String(progress.total)} answers`}
        </Status>
      );
    }
    case "clear":
      return <Status tone="ready">No Regressions</Status>;
    case "regressions":
      return (
        <>
          <Status tone="flagged">
            {regressions(evaluation.regressions.length)}
          </Status>
          <div className="basis-full pl-6">
            <RegressionList regressions={evaluation.regressions} />
          </div>
        </>
      );
  }
}

/** The selected Agents with Regressions, as a warning that never deselects or blocks them. */
function RegressionsWarning({
  evaluation,
  selected,
  version,
}: {
  evaluation: RolloutEvaluation;
  selected: string[];
  version: string;
}) {
  const names = evaluation.agents
    .filter(
      (agent) =>
        agent.state === "regressions" && selected.includes(agent.agent_id),
    )
    .map((agent) => agent.name);
  if (names.length === 0) return null;
  const verb = names.length === 1 ? "has" : "have";
  return (
    <Notice tone="warning">
      {`${names.join(", ")} ${verb} Regressions with Instructions ${version}: cases that pass on the Live Version fail with the new Instructions. You can still publish.`}
    </Notice>
  );
}

/**
 * The rollout dialog's Evaluate rollout action and each Agent's evaluation, by Agent ID. It runs
 * each selected Agent's Evaluation Set with its Live configuration and the new Instructions against
 * Live as it is; it informs the rollout and never blocks it.
 */
export function useRolloutEvaluationSection({
  organisationId,
  projectId,
  version,
  selected,
}: {
  organisationId: string;
  projectId: string;
  version: { id: string; number: number };
  selected: string[];
}) {
  const evaluation = useRolloutEvaluation(
    organisationId,
    projectId,
    version.id,
  );
  const start = useStartRolloutEvaluation(
    organisationId,
    projectId,
    version.id,
  );
  const byAgent = new Map(
    (evaluation.data?.agents ?? []).map((agent) => [agent.agent_id, agent]),
  );
  const running = [...byAgent.values()].some(
    (agent) => agent.state === "running",
  );
  const name = `v${String(version.number)}`;
  const failure = evaluationFailure(start.error);

  const section = (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className={text.muted}>
          {`Evaluate rollout runs each selected Agent's Evaluation Set with its Live configuration and Instructions ${name}, against its Live Version as it is.`}
        </p>
        <button
          type="button"
          className={button.secondary}
          disabled={selected.length === 0 || start.isPending || running}
          onClick={() => {
            start.mutate(selected);
          }}
        >
          {start.isPending || running ? "Evaluating…" : "Evaluate rollout"}
        </button>
      </div>
      {failure !== undefined && <Notice tone="error">{failure}</Notice>}
      {evaluation.isError && (
        <p className={text.muted}>
          The Rollout evaluation could not be loaded.
        </p>
      )}
      {evaluation.data && (
        <RegressionsWarning
          evaluation={evaluation.data}
          selected={selected}
          version={name}
        />
      )}
    </div>
  );
  return { section, byAgent };
}
