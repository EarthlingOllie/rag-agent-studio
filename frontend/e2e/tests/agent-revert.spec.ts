import { expect, test } from "../fixtures";
import { liveVersion, openAgentView } from "../fixtures/agent";
import { openSection } from "../fixtures/navigation";

test.describe("Revert an Agent via its Live History", () => {
  test("an Owner reverts an Agent to the Version Live before, restoring its pinned Instructions, shown in the Live History timeline and the Audit log", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    await page.goto("/");
    await openSection(page, "Organisation sections", "Projects");
    const newProject = page.getByRole("form", { name: "New Project" });
    await newProject.getByLabel("Name").fill("Reverting HR");
    await newProject.getByRole("button", { name: "Create Project" }).click();
    await openSection(page, "Project sections", "Agents");
    await page.getByRole("form", { name: "New Agent" }).getByLabel("Name").fill("HR helper");
    await page.getByRole("form", { name: "New Agent" }).getByRole("button", { name: "Create Agent" }).click();
    await expect(page.getByRole("heading", { level: 2, name: "HR helper" })).toBeVisible({ timeout: 15_000 });
    const agentApi = page.url().replace(/^https?:\/\/[^/]+/, "/api");
    await openAgentView(page, "Versions");
    await expect(page.getByText("Nothing has been Live yet. Publish the Draft to make v1 Live.")).toBeVisible();

    const projectApi = agentApi.replace(/\/agents\/[^/]+$/, "");
    const publishInstructions = async (markdown: string) => {
      expect((await page.request.put(`${projectApi}/instructions`, { data: { markdown } })).ok()).toBe(true);
      expect((await page.request.post(`${projectApi}/instructions/versions`, { data: { note: markdown } })).status()).toBe(201);
      await page.reload();
    };
    const publish = page.getByRole("form", { name: "Publish" });
    const publishAgent = async (note: string, instructions: number) => {
      await page.getByRole("banner").getByRole("button", { name: "Publish" }).click();
      const picker = publish.getByRole("combobox", { name: "Project Instructions" });
      await expect(picker.getByRole("option", { name: `Current Version (v${String(instructions)})` })).toHaveCount(1, {
        timeout: 15_000,
      });
      await publish.getByRole("textbox", { name: "Note" }).fill(note);
      await publish.getByRole("button", { name: "Publish" }).click();
      await expect(publish.getByRole("status")).toContainText(`with Instructions v${String(instructions)}`, { timeout: 15_000 });
      await page.getByRole("dialog").getByRole("button", { name: "Close" }).click();
    };

    // v1 pins Instructions v1; v2 pins Instructions v2.
    await publishInstructions("Be kind.");
    await publishAgent("First release", 1);
    await expect(page.getByText("There's no earlier Live Version to revert to: v1 was the first.")).toBeVisible();
    await publishInstructions("Be kind and brief.");
    await publishAgent("Second release", 2);
    await expect(liveVersion(page, 2)).toBeVisible();

    const timeline = page.getByRole("list", { name: "Live History" });
    await expect(timeline.getByRole("listitem")).toHaveCount(2);
    await expect(timeline.getByRole("listitem").nth(0)).toContainText("Published v1 → v2");
    await expect(timeline.getByRole("listitem").nth(1)).toContainText("Published v1");

    // Revert, from the Live Version's ⋯ menu, confirming first.
    await page.getByRole("button", { name: "Actions for the Live Version" }).click();
    await page.getByRole("menuitem", { name: "Revert to v1" }).click();
    const confirm = page.getByRole("dialog", { name: "Revert to v1?" });
    await expect(confirm).toContainText("Visitors are served v1 with the Instructions it pins at once.");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    await confirm.getByRole("button", { name: "Yes, revert to v1" }).click();

    await expect(page.getByText("Reverted to v1 with Instructions v1. It is now Live.")).toBeVisible({ timeout: 15_000 });
    await expect(liveVersion(page, 1)).toBeVisible();
    await expect(timeline.getByRole("listitem")).toHaveCount(3);
    await expect(timeline.getByRole("listitem").nth(0)).toContainText("Reverted v2 → v1");
    await expect(page.getByText("There's no earlier Live Version to revert to: v1 was the first.")).toBeVisible();
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // The API agrees: v1 is Live with Instructions v1, and a further revert is refused.
    const versions = (await (await page.request.get(`${agentApi}/versions`)).json()) as {
      live_version_id: string;
      versions: { id: string; number: number; instructions_version: { number: number } }[];
    };
    const live = versions.versions.find((v) => v.id === versions.live_version_id);
    expect([live?.number, live?.instructions_version.number]).toEqual([1, 1]);
    const refused = await page.request.post(`${agentApi}/revert`);
    expect(refused.status()).toBe(409);
    expect(((await refused.json()) as { detail: string }).detail).toBe("There's no earlier Live Version to revert to.");

    const organisationId = agentApi.split("/")[3] ?? "";
    const audit = await page.request.get(`/api/organisations/${organisationId}/audit-events`, {
      params: { action: "agent.reverted" },
    });
    const items = (
      (await audit.json()) as {
        items: { before: { live_version: { number: number } }; after: { live_version: { number: number } } }[];
      }
    ).items;
    expect(items.map((item) => [item.before.live_version.number, item.after.live_version.number])).toEqual([[2, 1]]);
  });
});
