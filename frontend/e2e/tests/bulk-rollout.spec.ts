import type { Page } from "@playwright/test";

import { expect, test } from "../fixtures";
import { openSection } from "../fixtures/navigation";

type Versions = { live_version_id: string; versions: { id: string; number: number; instructions_version: { number: number } | null }[] };

/** The Agent's Live Version number and the Instructions Version it pins, as the API reports them. */
async function live(page: Page, agentApi: string): Promise<[number | undefined, number | undefined]> {
  const listed = (await (await page.request.get(`${agentApi}/versions`)).json()) as Versions;
  const found = listed.versions.find((version) => version.id === listed.live_version_id);
  return [found?.number, found?.instructions_version?.number];
}

test.describe("Bulk publish, bulk revert and the Instructions rollout", () => {
  test("an Owner rolls Instructions v2 out to one of two Agents, sees the other behind, reverts the first from the Agent list, then bulk-reverts after reverting the Instructions", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    await page.goto("/");
    await openSection(page, "Organisation sections", "Projects");
    const newProject = page.getByRole("form", { name: "New Project" });
    await newProject.getByLabel("Name").fill("Rollout HR");
    await newProject.getByRole("button", { name: "Create Project" }).click();
    await openSection(page, "Project sections", "Instructions");
    await expect(page.getByText("Not published yet. Publish the Draft to make v1, the Current Version.")).toBeVisible({
      timeout: 15_000,
    });
    const projectApi = page.url().replace(/^https?:\/\/[^/]+/, "/api").replace(/\/instructions$/, "");

    // Instructions v1, and two Agents published with it through the API.
    expect((await page.request.put(`${projectApi}/instructions`, { data: { markdown: "Be kind." } })).ok()).toBe(true);
    expect((await page.request.post(`${projectApi}/instructions/versions`, { data: { note: "First rules" } })).status()).toBe(201);
    const agentApis: Record<string, string> = {};
    for (const name of ["Agent A", "Agent B"]) {
      const created = await page.request.post(`${projectApi}/agents`, { data: { name } });
      expect(created.status()).toBe(201);
      agentApis[name] = `${projectApi}/agents/${((await created.json()) as { id: string }).id}`;
      expect((await page.request.post(`${agentApis[name]}/versions`, { data: { note: "First release" } })).status()).toBe(201);
    }
    const agentA = agentApis["Agent A"] ?? "";
    const agentB = agentApis["Agent B"] ?? "";
    // Agent B gets an unpublished Draft edit, which a rollout must not ship.
    expect((await page.request.put(`${agentB}/draft`, { data: { behaviour: { system_prompt: "Unreviewed." } } })).ok()).toBe(true);
    await page.reload();
    await expect(page.getByText(/behind the Current Version/)).toHaveText("0 Agents behind the Current Version v1", { timeout: 15_000 });

    // Publish Instructions v2 in the Studio: the rollout dialog opens with both Agents selected.
    await page.getByRole("button", { name: "Markdown" }).click();
    await page.getByRole("textbox", { name: "Project Instructions (Markdown)" }).fill("Be kind and brief.");
    const publishForm = page.getByRole("form", { name: "Publish Instructions" });
    await publishForm.getByRole("textbox", { name: "Note" }).fill("Brevity");
    await publishForm.getByRole("button", { name: "Publish Instructions" }).click();
    const dialog = page.getByRole("dialog", { name: "Roll out Instructions v2" });
    await expect(dialog.getByRole("checkbox", { name: "Agent A" })).toBeChecked({ timeout: 15_000 });
    await expect(dialog.getByRole("checkbox", { name: "Agent B" })).toBeChecked();
    const agentBRow = dialog.getByRole("listitem").filter({ hasText: "Agent B" });
    await expect(agentBRow.getByText("Draft", { exact: true })).toBeVisible();
    await expect(agentBRow).toContainText("changes not included");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // Adopt on Agent A only.
    await dialog.getByRole("checkbox", { name: "Agent B" }).uncheck();
    await dialog.getByRole("button", { name: "Publish to 1 Agent" }).click();
    const results = dialog.getByRole("list", { name: "Results" });
    await expect(results).toContainText("Agent A — Done: Published v2 with Instructions v2. It is now Live.", { timeout: 15_000 });
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    await dialog.getByRole("button", { name: "Done" }).click();

    // Agent A serves Instructions v2; Agent B is behind on v1.
    await expect(page.getByText(/behind the Current Version/)).toHaveText("1 Agent behind the Current Version v2", { timeout: 15_000 });
    const table = page.getByRole("table", { name: "Instructions each Agent runs with" });
    await expect(table.getByRole("row", { name: /Agent A/ })).toContainText("v2v2");
    await expect(table.getByRole("row", { name: /Agent B/ })).toContainText("v1Instructions behind");
    expect(await live(page, agentA)).toEqual([2, 2]);
    expect(await live(page, agentB)).toEqual([1, 1]);
    // The bulk publish built Agent A's v2 from its Live config, and Agent B's Draft edit stayed in its Draft.
    const agentBVersions = (await (await page.request.get(`${agentB}/versions`)).json()) as Versions;
    expect(agentBVersions.versions).toHaveLength(1);

    // Revert Agent A from the Agent list with multi-select: it serves Instructions v1 again.
    await openSection(page, "Project sections", "Agents");
    await page.getByRole("checkbox", { name: "Select Agent A" }).check({ timeout: 15_000 });
    await page.getByRole("button", { name: "Revert selected (1)" }).click();
    await page.getByRole("button", { name: "Yes, revert 1 Agent" }).click();
    await expect(page.getByRole("list", { name: "Results" })).toContainText(
      "Agent A — Done: Reverted to v1 with Instructions v1. It is now Live.",
      { timeout: 15_000 },
    );
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    expect(await live(page, agentA)).toEqual([1, 1]);

    // Roll v2 out to both from the "behind" summary, then revert the Instructions: the Studio
    // offers to bulk-revert the Agents pinned to v2.
    await openSection(page, "Project sections", "Instructions");
    await expect(page.getByText(/behind the Current Version/)).toHaveText("2 Agents behind the Current Version v2", { timeout: 15_000 });
    await page.getByRole("button", { name: "Roll out v2…" }).click();
    await dialog.getByRole("button", { name: "Publish to 2 Agents" }).click();
    await expect(results.getByRole("listitem")).toHaveCount(2, { timeout: 15_000 });
    await dialog.getByRole("button", { name: "Done" }).click();
    await expect(page.getByText(/behind the Current Version/)).toHaveText("0 Agents behind the Current Version v2", { timeout: 15_000 });

    await page.getByRole("button", { name: "Revert to v1" }).click();
    await page.getByRole("alertdialog", { name: "Revert to v1?" }).getByRole("button", { name: "Yes, revert to v1" }).click();
    const offer = page.getByRole("dialog", { name: "Revert the Agents on Instructions v2?" });
    await expect(offer.getByRole("checkbox", { name: "Agent A (Live v3)" })).toBeChecked({ timeout: 15_000 });
    await expect(offer.getByRole("checkbox", { name: "Agent B (Live v2)" })).toBeChecked();
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    await offer.getByRole("button", { name: "Revert 2 Agents" }).click();
    await expect(offer.getByRole("list", { name: "Results" }).getByRole("listitem")).toHaveCount(2, { timeout: 15_000 });
    await offer.getByRole("button", { name: "Done" }).click();
    await expect(page.getByText(/behind the Current Version/)).toHaveText("0 Agents behind the Current Version v1", { timeout: 15_000 });
    expect(await live(page, agentA)).toEqual([1, 1]);
    expect(await live(page, agentB)).toEqual([1, 1]);

    // Each bulk action's ID is on the Live History and in the Audit log.
    const history = (await (await page.request.get(`${agentA}/live-history`)).json()) as {
      action: string;
      bulk_operation_id: string | null;
    }[];
    expect(history.map((entry) => entry.action)).toEqual(["bulk_revert", "bulk_publish", "bulk_revert", "bulk_publish", "publish"]);
    expect(history.slice(0, 4).every((entry) => entry.bulk_operation_id !== null)).toBe(true);
    const organisationId = projectApi.split("/")[3] ?? "";
    const audit = await page.request.get(`/api/organisations/${organisationId}/audit-events`, {
      params: { action: "project.agents_bulk_published" },
    });
    const items = ((await audit.json()) as { items: { after: { bulk_operation_id: string; succeeded: number } }[] }).items;
    expect(items.map((item) => item.after.succeeded)).toEqual([2, 1]);
    expect(items.map((item) => item.after.bulk_operation_id)).toContain(history[1]?.bulk_operation_id);
  });
});
