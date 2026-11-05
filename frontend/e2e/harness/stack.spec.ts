import { expect, test } from "@playwright/test";

import { waitForStack } from "../fixtures/stack";
import { startFakeStudio } from "./fake-studio";

test.describe("stack readiness", () => {
  test("waits until the API and the worker report healthy", async () => {
    const studio = await startFakeStudio({ apiUnhealthyFor: 3 });
    try {
      await waitForStack({ baseURL: studio.url, timeoutMs: 5_000, intervalMs: 10 });
      expect(studio.healthRequests()).toBe(4);
    } finally {
      await studio.close();
    }
  });

  test("fails naming the check that never became healthy", async () => {
    const studio = await startFakeStudio({ workerHealthy: false });
    try {
      await expect(waitForStack({ baseURL: studio.url, timeoutMs: 200, intervalMs: 10 })).rejects.toThrow(
        `The stack at ${studio.url} was not healthy within 200 ms: /api/health/worker answered 503`,
      );
    } finally {
      await studio.close();
    }
  });

  test("fails when nothing is listening", async () => {
    const studio = await startFakeStudio();
    await studio.close();
    await expect(waitForStack({ baseURL: studio.url, timeoutMs: 200, intervalMs: 10 })).rejects.toThrow(
      /was not healthy within 200 ms: \/ is unreachable/,
    );
  });
});
