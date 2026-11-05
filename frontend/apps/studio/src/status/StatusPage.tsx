import { useHealth, useWorkerHealth } from "./health";

type State = "ok" | "error" | "pending";

const LABELS: Record<State, string> = { ok: "OK", error: "Unavailable", pending: "Checking…" };
const TONES: Record<State, string> = {
  ok: "bg-emerald-100 text-emerald-800",
  error: "bg-red-100 text-red-800",
  pending: "bg-slate-100 text-slate-600",
};

function StatusRow({ name, state, detail }: { name: string; state: State; detail?: string }) {
  return (
    <tr className="border-t border-slate-200">
      <th scope="row" className="py-3 pr-6 text-left font-medium">
        {name}
      </th>
      <td className="py-3 pr-6">
        <span className={`rounded px-2 py-0.5 text-sm ${TONES[state]}`}>{LABELS[state]}</span>
      </td>
      <td className="py-3 text-sm text-slate-600">{detail}</td>
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
    <section aria-labelledby="status-heading" className="space-y-6">
      <div>
        <h1 id="status-heading" className="text-2xl font-semibold">
          System status
        </h1>
        <p className="mt-1 text-slate-600" role="status">
          {summary}
        </p>
      </div>
      <table className="w-full rounded-lg bg-white">
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
