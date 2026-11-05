import createClient from "openapi-fetch";

import type { components, paths } from "./schema.gen";

export type { components, paths };
export type Schemas = components["schemas"];
export type ApiClient = ReturnType<typeof createClient<paths>>;

/** A typed client for the Studio API, generated from the backend's OpenAPI schema. */
export function createApiClient(baseUrl: string): ApiClient {
  // Resolve fetch per request rather than capturing it once, so the client always uses the
  // current global (for example after a network-layer mock is installed).
  return createClient<paths>({ baseUrl, fetch: (request) => globalThis.fetch(request) });
}
