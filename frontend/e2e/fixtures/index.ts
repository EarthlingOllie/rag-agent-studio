import AxeBuilder from "@axe-core/playwright";
import { test as base, type Page } from "@playwright/test";

import { type MemberCredentials, newMember, signInAs, signUp } from "./auth";
import { STACK_TIMEOUT_MS, STUDIO_URL } from "./env";
import { waitForStack } from "./stack";

/** WCAG 2.2 AA, the level the Studio and the widget are held to. */
export const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

interface WorkerFixtures {
  /** Studio URL whose health is awaited once per worker. */
  stackURL: string;
  /** Waits for stack readiness before a worker's first test. */
  stack: undefined;
}

interface TestFixtures {
  /** A fresh Member, not yet signed up. */
  member: MemberCredentials;
  /** A page signed in as `member`, who has just signed up and so owns a new Organisation. */
  signedInPage: Page;
  /** Builds an axe scan of `page` limited to WCAG 2.2 AA rules. */
  makeAxeBuilder: () => AxeBuilder;
}

/** The test function every end-to-end spec imports instead of Playwright's own. */
export const test = base.extend<TestFixtures, WorkerFixtures>({
  stackURL: [STUDIO_URL, { scope: "worker", option: true }],
  stack: [
    async ({ stackURL }, use) => {
      await waitForStack({ baseURL: stackURL, timeoutMs: STACK_TIMEOUT_MS });
      await use(undefined);
    },
    { scope: "worker", auto: true },
  ],
  // eslint-disable-next-line no-empty-pattern -- Playwright requires a destructuring pattern here.
  member: async ({}, use) => {
    await use(newMember());
  },
  signedInPage: async ({ page, member }, use) => {
    await signUp(page.request, member);
    await signInAs(page, member);
    await use(page);
  },
  makeAxeBuilder: async ({ page }, use) => {
    await use(() => new AxeBuilder({ page }).withTags(AXE_TAGS));
  },
});

export { expect } from "@playwright/test";
