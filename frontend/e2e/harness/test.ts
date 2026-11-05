import { test as studioTest } from "../fixtures";
import { type FakeStudio, startFakeStudio } from "./fake-studio";

/** The shared Studio fixtures, pointed at an in-process fake Studio instead of the compose stack. */
export const test = studioTest.extend<{ studio: FakeStudio }, { workerStudio: FakeStudio }>({
  workerStudio: [
    // eslint-disable-next-line no-empty-pattern -- Playwright requires a destructuring pattern here.
    async ({}, use) => {
      const studio = await startFakeStudio();
      await use(studio);
      await studio.close();
    },
    { scope: "worker" },
  ],
  stackURL: [async ({ workerStudio }, use) => use(workerStudio.url), { scope: "worker" }],
  studio: async ({ workerStudio }, use) => use(workerStudio),
  baseURL: async ({ workerStudio }, use) => use(workerStudio.url),
});

export { expect } from "../fixtures";
