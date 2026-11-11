import { Status, table } from "../design";
import { useHealth, useWorkerHealth } from "./health";

type State = "ok" | "error" | "pending";

const LABELS: Record<State, string> = { ok: "OK", error: "Unavailable", pending: "Checking…" };
const TONES = { ok: "ready", error: "failed", pending: "working" } as const;

/** One dependency: its name, a `Status` dot with the word, and what it said. */
function StatusRow({ name, state, detail }: { name: string; state: State; detail?: string }) {
  return (
    <tr className={table.row}>
      <th scope="row" className={`${table.td} text-left font-medium`}>
        {name}
      </th>
      <td className={table.td}>
        <Status tone={TONES[state]}>{LABELS[state]}</Status>
      </td>
      <td className={table.tdMuted}>{detail}</td>
    </tr>
  );
}

export function StatusPage() {
  const health = useHealth();
  const worker = useWorkerHealth();

  const apiState: State = health.isPending ? "pending" : health.isError ? "error" : "ok";
  const checks = health.data?.checks;
  const dependencyState = (check: "ok" | "error" | undefined): State =>
    check ?? (health.isError ? "error" : "pending");
  const workerState: State = worker.isPending
    ? "pending"
    : worker.data?.status === "ok"
      ? "ok"
      : "error";

  let summary = "Checking…";
  if (health.isError) {
    summary = "The API could not be reached";
  } else if (health.data) {
    summary =
      health.data.status === "ok" && workerState !== "error"
        ? "All systems operational"
        : "Some systems are unavailable";
  }

  return (
    <section aria-labelledby="status-heading" className="flex flex-col gap-6">
      <div>
        <h1 id="status-heading" className="text-2xl font-medium tracking-[-0.01em] text-ink">
          System status
        </h1>
        <p className="mt-1 text-sm text-muted" role="status">
          {summary}
        </p>
      </div>
      <table className={`${table.table} border-b border-line-soft`}>
        <tbody>
          <StatusRow name="API" state={apiState} />
          <StatusRow name="Database" state={dependencyState(checks?.database)} />
          <StatusRow name="Redis" state={dependencyState(checks?.redis)} />
          <StatusRow
            name="Worker"
            state={workerState}
            {...(workerState === "pending"
              ? {}
              : {
                  detail:
                    workerState === "ok"
                      ? `Worker replied: ${String(worker.data?.reply)}`
                      : "Worker did not reply",
                })}
          />
        </tbody>
      </table>
    </section>
  );
}
