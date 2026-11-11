import { createApiClient } from "@studio/api-client";

/** The Studio is served from the same origin as the API (Vite proxy locally, CloudFront in AWS). */
export const api = createApiClient(window.location.origin);
