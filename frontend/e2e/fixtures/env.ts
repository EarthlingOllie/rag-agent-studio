/** Where the Studio of the stack under test is served. The Studio proxies /api to the API. */
export const STUDIO_URL = process.env.E2E_BASE_URL ?? "http://localhost:5173";

/** How long to wait for the stack's health checks before failing the run. */
export const STACK_TIMEOUT_MS = Number(process.env.E2E_STACK_TIMEOUT_MS ?? 180_000);

/** Mailpit's web and API address for the stack under test; the stack's email lands there. */
export const MAILPIT_URL = process.env.E2E_MAILPIT_URL ?? "http://localhost:8025";

/** The demo host page: a separate origin that pastes an Agent's Embed Snippet (`?agent=agt_…`). */
export const HOST_URL = process.env.E2E_HOST_URL ?? "http://localhost:5175";

/** The demo host's second origin, which no Agent allows: its page tries to embed the Product FAQ and is refused. */
export const BLOCKED_HOST_URL = process.env.E2E_BLOCKED_HOST_URL ?? "http://localhost:5176";
