import { expect, test } from "../fixtures";
import { openSection } from "../fixtures/navigation";

test.describe("Publish an Agent to its Live Version", () => {
  test("an Owner publishes a not-live Agent pinning the Current Instructions, and it goes Live, recorded in the Live History and the Audit log", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    await page.goto("/");
    await openSection(page, "Organisation sections", "Projects");
    const newProject = page.getByRole("form", { name: "New Project" });
    await newProject.getByLabel("Name").fill("Publishing HR");
    await newProject.getByRole("button", { name: "Create Project" }).click();
    await openSection(page, "Project sections", "Agents");
    await page.getByRole("form", { name: "New Agent" }).getByLabel("Name").fill("HR helper");
    await page.getByRole("form", { name: "New Agent" }).getByRole("button", { name: "Create Agent" }).click();
    await expect(page.getByRole("heading", { level: 2, name: "HR helper" })).toBeVisible({ timeout: 15_000 });

    // Never published: not live.
    await expect(page.getByText("Not live")).toBeVisible();
    await expect(page.getByText("Visitors can't use it until you publish it.")).toBeVisible();
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // The Project publishes its Instructions v1, which becomes Current.
    const agentApi = page.url().replace(/^https?:\/\/[^/]+/, "/api");
    const projectApi = agentApi.replace(/\/agents\/[^/]+$/, "");
    expect((await page.request.put(`${projectApi}/instructions`, { data: { markdown: "Be kind." } })).ok()).toBe(true);
    expect((await page.request.post(`${projectApi}/instructions/versions`, { data: { note: "Rules" } })).status()).toBe(201);
    await page.reload();

    const publish = page.getByRole("form", { name: "Publish" });
    const picker = publish.getByRole("combobox", { name: "Project Instructions" });
    await expect(picker.getByRole("option", { name: "Current Version (v1)" })).toHaveCount(1, { timeout: 15_000 });
    await publish.getByRole("textbox", { name: "Note" }).fill("First release");
    await publish.getByRole("button", { name: "Publish" }).click();
    await expect(publish.getByRole("status")).toHaveText("Published v1 with Instructions v1. It is now Live.", {
      timeout: 15_000,
    });
    await expect(page.getByText("Live v1")).toBeVisible();
    await expect(page.getByText("Not live")).toHaveCount(0);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    await page.getByRole("link", { name: "All Agents" }).click();
    await expect(page.getByRole("list", { name: "Agents" }).getByRole("listitem")).toContainText("Live v1");

    // The API agrees: v1 is Live, pins Instructions v1, and the Live History and Audit log record it.
    const versions = (await (await page.request.get(`${agentApi}/versions`)).json()) as {
      live_version_id: string;
      versions: { id: string; number: number; note: string; instructions_version: { number: number } }[];
    };
    expect(versions.versions.map((v) => [v.number, v.note, v.instructions_version.number])).toEqual([[1, "First release", 1]]);
    expect(versions.live_version_id).toBe(versions.versions[0]?.id);
    const history = (await (await page.request.get(`${agentApi}/live-history`)).json()) as {
      from_version: null;
      to_version: { number: number };
      action: string;
    }[];
    expect(history.map((entry) => [entry.from_version, entry.to_version.number, entry.action])).toEqual([[null, 1, "publish"]]);
    const organisationId = agentApi.split("/")[3] ?? "";
    const audit = await page.request.get(`/api/organisations/${organisationId}/audit-events`, {
      params: { action: "agent.published" },
    });
    const items = ((await audit.json()) as { items: { after: { live_version: { number: number; note: string } } }[] }).items;
    expect(items.map((item) => [item.after.live_version.number, item.after.live_version.note])).toEqual([[1, "First release"]]);
  });
});
