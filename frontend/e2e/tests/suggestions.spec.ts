import type { APIRequestContext, Page } from "@playwright/test";

import { expect, test } from "../fixtures";
import { openAgentView } from "../fixtures/agent";
import { signInAs } from "../fixtures/auth";
import { openSection } from "../fixtures/navigation";

// `make seed` runs before the suite (`make e2e`). The stack answers, judges and proposes with the
// demo model, by rule: told not to quote the handbook it answers with one uncited sentence, its
// judge fails grounding when a reply cites nothing, and asked to propose a Suggestion it adds
// "Always cite the passage you used." to the system prompt when evidence failed grounding, and
// names a Knowledge Base gap for each failed reply that cited no Chunk. On the morning of the
// revert the seed had a Suggestion made from HR helper v2's failures; the Organisation keeps
// Message text for 14 days, so its oldest evidence was purged since.
const OWNER = { email: "owner@northwind.example", password: "northwind-owner-demo" };
const CURT_PROMPT = "Answer staff questions in one short sentence. Don't quote the handbook.";
const CITE_LINE = "Always cite the passage you used.";
const BOOT = /<script id="widget-boot" type="application\/json">(.*?)<\/script>/;

interface Draft {
  behaviour: Record<string, unknown>;
  retrieval: Record<string, unknown>;
  [section: string]: unknown;
}

async function json<T>(request: APIRequestContext, method: "GET" | "POST" | "PUT" | "PATCH", url: string, data?: unknown): Promise<T> {
  const response = await request.fetch(url, { method, data });
  expect(response.ok(), `${method} ${url}: ${await response.text()}`).toBe(true);
  return (await response.json()) as T;
}

async function openSuggestions(page: Page) {
  await openAgentView(page, "Evaluation");
  await page.getByRole("radiogroup", { name: "Evaluation view" }).getByRole("radio", { name: "Suggestions" }).click();
  await expect(page.getByRole("heading", { level: 2, name: "Suggestions" })).toBeVisible({ timeout: 15_000 });
}

test.describe("Suggestions", () => {
  test("the HR helper's seeded Suggestion shows its check, a Knowledge Base gap and purged evidence", async ({ page, makeAxeBuilder }) => {
    await signInAs(page, OWNER);
    await page.goto("/");
    await openSection(page, "Organisation sections", "Projects");
    await page.getByRole("link", { name: "Northwind Handbook" }).click();
    await openSection(page, "Project sections", "Agents");
    await page.getByRole("link", { name: "HR helper", exact: true }).click();
    await expect(page.getByRole("heading", { level: 1, name: "HR helper" })).toBeVisible({ timeout: 15_000 });

    await test.step("the Suggestions tab lists the Suggestion made from v2, stale since v1 replaced it", async () => {
      await openSuggestions(page);
      const seeded = page.getByRole("list", { name: "Suggestion runs" }).getByRole("listitem").filter({ hasText: "From Version 2" });
      await expect(seeded).toHaveCount(1, { timeout: 15_000 });
      await expect(seeded).toContainText("Completed");
      await expect(seeded).toContainText("Changes suggested");
      await expect(seeded).toContainText("Stale");
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
      await seeded.getByRole("button", { name: /^Suggestion of / }).click();
    });

    await test.step("its detail: the system prompt change, its check, a gap and \"Text purged\" evidence", async () => {
      await expect(page.getByText("Made from Version 2, which is no longer Live: its check was against the old Live Version. You can still apply it.")).toBeVisible({
        timeout: 15_000,
      });
      const change = page.getByRole("table", { name: "Suggested change to the system prompt" });
      await expect(change).toContainText(CITE_LINE);
      const check = page.getByRole("region", { name: "Check against the Evaluation Set" });
      await expect(check).toContainText(/Version 2: \d+% · Suggestion: \d+%/);
      await expect(check.getByRole("link", { name: "Open the check in Run detail" })).toBeVisible();
      await expect(page.getByRole("list", { name: "Knowledge Base gaps" }).getByRole("listitem").first()).toBeVisible();
      const evidence = page.getByRole("list", { name: "Evidence", exact: true });
      await expect(evidence.getByRole("link").filter({ hasText: "Text purged" }).first()).toBeVisible();
      await expect(evidence.getByRole("link").filter({ hasText: "Evaluation Case failed" }).first()).toBeVisible();
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    });
  });

  test("an Owner starts a Suggestion run, applies it to the Draft, and the Publish dialog asks for a new Evaluation Run", async ({
    page,
    browser,
    makeAxeBuilder,
  }) => {
    test.setTimeout(420_000);
    await signInAs(page, OWNER);
    await page.goto("/");
    const me = await json<{ organisations: { id: string; name: string }[] }>(page.request, "GET", "/api/auth/me");
    const organisation = `/api/organisations/${me.organisations.find((each) => each.name === "Northwind Traders")?.id ?? ""}`;
    const projects = await json<{ id: string; name: string }[]>(page.request, "GET", `${organisation}/projects`);
    const projectId = projects.find((each) => each.name === "Northwind Handbook")?.id ?? "";
    const project = `${organisation}/projects/${projectId}`;
    // An Agent of this run's own, so the seeded HR helper's Versions stay as the other tests expect.
    const name = `Curt HR helper (run ${String(Date.now())})`;
    const created = await json<{ id: string; public_id: string; draft: Draft }>(page.request, "POST", `${project}/agents`, { name });
    const agentApi = `${project}/agents/${created.id}`;

    try {
      await test.step("publish it with a curt system prompt, judge every reply, and evaluate it once", async () => {
        const tags = await json<{ id: string; name: string }[]>(page.request, "GET", `${project}/tags`);
        const hr = tags.find((each) => each.name === "HR")?.id ?? "";
        await json(page.request, "PUT", `${agentApi}/draft`, {
          ...created.draft,
          behaviour: { ...created.draft.behaviour, system_prompt: CURT_PROMPT },
          retrieval: { ...created.draft.retrieval, tag_ids: [hr] },
        });
        await json(page.request, "POST", `${agentApi}/versions`, { note: "Short answers" });
        await json(page.request, "PATCH", `${agentApi}/operational-settings`, { live_sample_rate: 100 });
        await json(page.request, "POST", `${agentApi}/evaluation/cases`, {
          question: "How many days of annual leave do I get?",
          reference_answer: 'Everyone gets "25 days of annual leave" a year.',
          expected_sources: [],
          expect_fallback: false,
          source: "written",
        });
        const run = await json<{ id: string }>(page.request, "POST", `${agentApi}/evaluation/runs`, { sides: null });
        await expect
          .poll(async () => (await json<{ status: string }>(page.request, "GET", `${agentApi}/evaluation/runs/${run.id}`)).status, { timeout: 120_000 })
          .toBe("completed");
      });

      await test.step("a Visitor's reply cites nothing, and its Live Verdict fails", async () => {
        const visitor = await browser.newContext();
        const shell = await (await visitor.request.get(`/widget/a/${created.public_id}`)).text();
        const boot = JSON.parse(BOOT.exec(shell)?.[1] ?? "{}") as { bootstrap_token: string };
        const started = await visitor.request.post(`/api/widget/agents/${created.public_id}/conversations`, {
          data: { bootstrap_token: boot.bootstrap_token },
        });
        expect(started.status()).toBe(201);
        const { conversation_token: token } = (await started.json()) as { conversation_token: string };
        const asked = await visitor.request.post(`/api/widget/agents/${created.public_id}/messages`, {
          data: { content: "Can I carry leave over to next year?" },
          headers: { Authorization: `Bearer ${token}` },
        });
        expect(asked.status()).toBe(200);
        await visitor.close();
        // The worker judges it in the background.
        await expect
          .poll(async () => (await json<{ live_verdict: number }>(page.request, "GET", `${agentApi}/suggestions/evidence`)).live_verdict, { timeout: 60_000 })
          .toBe(1);
      });

      await page.goto(agentApi.replace(/^\/api/, ""));
      await expect(page.getByRole("heading", { level: 1, name })).toBeVisible({ timeout: 15_000 });

      await test.step("Suggest changes: the dialog counts the evidence, and the run proposes asking for citations", async () => {
        await openSuggestions(page);
        await expect(page.getByRole("heading", { name: "No Suggestions yet" })).toBeVisible({ timeout: 15_000 });
        await page.getByRole("button", { name: "Suggest changes" }).click();
        const dialog = page.getByRole("dialog", { name: "Suggest changes" });
        await expect(dialog.getByRole("status", { name: "Evidence in the range" })).toContainText("1", { timeout: 15_000 });
        await expect(dialog.getByRole("status", { name: "Estimated Cost" })).toBeVisible();
        expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
        await dialog.getByRole("button", { name: "Start Suggestion run" }).click();
        const runs = page.getByRole("list", { name: "Suggestion runs" });
        await expect(runs.getByRole("listitem").first()).toContainText("Completed", { timeout: 180_000 });
        await expect(page.getByRole("table", { name: "Suggested change to the system prompt" })).toContainText(CITE_LINE);
        const check = page.getByRole("region", { name: "Check against the Evaluation Set" });
        await expect(check).toContainText(/Version 1: \d+% · Suggestion: \d+%/, { timeout: 120_000 });
        await expect(page.getByRole("list", { name: "Knowledge Base gaps" }).getByRole("listitem")).toHaveCount(1);
        expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
      });

      await test.step("Apply to Draft writes the change, and the Publish dialog asks for a new Evaluation Run", async () => {
        await page.getByRole("button", { name: "Apply to Draft" }).click();
        const review = page.getByRole("dialog", { name: "Apply to Draft" });
        await expect(review.getByRole("list", { name: "Changes to the Draft" })).toContainText("Will be applied", { timeout: 15_000 });
        expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
        await review.getByRole("button", { name: "Apply to Draft" }).click();
        await expect(page.getByText("Applied to the Draft. Evaluate it again before Publishing.")).toBeVisible({ timeout: 15_000 });
        const agent = await json<{ draft: Draft }>(page.request, "GET", agentApi);
        expect(agent.draft.behaviour.system_prompt).toBe(`${CURT_PROMPT}\n${CITE_LINE}`);

        await page.getByRole("banner").getByRole("button", { name: "Publish" }).click();
        const evaluation = page.getByRole("form", { name: "Publish" }).getByRole("region", { name: "Evaluation" });
        await expect(evaluation.getByText(/The Draft has changed since it was evaluated/)).toBeVisible({ timeout: 15_000 });
        await expect(evaluation.getByRole("button", { name: "Evaluate" })).toBeVisible();
        expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
        await page.getByRole("dialog").getByRole("button", { name: "Close" }).click();
      });
    } finally {
      // The run's Agent goes (Owners delete Agents), so the demo Project is left as seeded.
      await page.request.post(`${agentApi}/archive`);
      await page.request.delete(agentApi, { data: { confirm_name: name } });
    }
  });
});
