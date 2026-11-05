/** Where the Studio of the stack under test is served. The Studio proxies /api to the API. */
export const STUDIO_URL = process.env.E2E_BASE_URL ?? "http://localhost:5173";

/** How long to wait for the stack's health checks before failing the run. */
export const STACK_TIMEOUT_MS = Number(process.env.E2E_STACK_TIMEOUT_MS ?? 180_000);
