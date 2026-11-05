/**
 * Stack readiness: the Studio page loads, and through the Studio's /api proxy the API reports its
 * database and Redis as ok and a Celery worker answers the health task.
 */
export interface StackReadinessOptions {
  baseURL: string;
  timeoutMs: number;
  intervalMs?: number;
}

const HEALTH_CHECKS = ["/", "/api/health", "/api/health/worker"] as const;

async function problemWith(baseURL: string, path: string): Promise<string | null> {
  let response: Response;
  try {
    response = await fetch(new URL(path, baseURL));
  } catch {
    return `${path} is unreachable`;
  }
  if (!response.ok) return `${path} answered ${String(response.status)}`;
  if (path === "/") return null;
  const body = (await response.json()) as { status?: unknown };
  return body.status === "ok" ? null : `${path} reported ${JSON.stringify(body)}`;
}

async function firstProblem(baseURL: string): Promise<string | null> {
  for (const path of HEALTH_CHECKS) {
    const problem = await problemWith(baseURL, path);
    if (problem !== null) return problem;
  }
  return null;
}

/** Resolves once every health check passes; rejects with the last failing check after `timeoutMs`. */
export async function waitForStack({ baseURL, timeoutMs, intervalMs = 1_000 }: StackReadinessOptions): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const problem = await firstProblem(baseURL);
    if (problem === null) return;
    if (Date.now() >= deadline) {
      throw new Error(`The stack at ${baseURL} was not healthy within ${String(timeoutMs)} ms: ${problem}`);
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}
