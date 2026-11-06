import { expect, test } from "../fixtures";

test.describe("Diffs and Draft management", () => {
  test("an Owner reviews the Draft against the Live Version, discards it, starts it from an earlier Version, compares Versions and resolves a colleague's conflicting save", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    await page.goto("/");
    await page.getByRole("navigation", { name: "Organisation" }).getByRole("link", { name: "Projects" }).click();
    const newProject = page.getByRole("form", { name: "New Project" });
    await newProject.getByLabel("Name").fill("Drafts HR");
    await newProject.getByRole("button", { name: "Create Project" }).click();
    await page.getByRole("navigation", { name: "Project" }).getByRole("link", { name: "Agents" }).click();
    await page.getByRole("form", { name: "New Agent" }).getByLabel("Name").fill("HR helper");
    await page.getByRole("form", { name: "New Agent" }).getByRole("button", { name: "Create Agent" }).click();
    await expect(page.getByRole("heading", { level: 2, name: "HR helper" })).toBeVisible({ timeout: 15_000 });
    const agentApi = page.url().replace(/^https?:\/\/[^/]+/, "/api");

    // v1 and v2 are published through the API; then the Draft is edited.
    const prompt = (system_prompt: string) => ({ behaviour: { system_prompt } });
    const publish = async (system_prompt: string, note: string) => {
      expect((await page.request.put(`${agentApi}/draft`, { data: prompt(system_prompt) })).ok()).toBe(true);
      expect((await page.request.post(`${agentApi}/versions`, { data: { note } })).status()).toBe(201);
    };
    await publish("Answer from the handbook.", "First release");
    await publish("Answer from the handbook.\nBe brief.", "Shorter answers");
    expect((await page.request.put(`${agentApi}/draft`, { data: prompt("Answer from the handbook.\nBe very brief.") })).ok()).toBe(true);
    await page.reload();

    // The badge, and the publish dialog's Draft-to-Live diff.
    await expect(page.getByText("Live v2")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("Unpublished changes")).toBeVisible();
    const changes = page.getByRole("region", { name: "Changes to publish" });
    const promptChanges = changes.getByRole("list", { name: "Behaviour › System prompt changes" });
    await expect(promptChanges.getByRole("listitem")).toHaveText(
      ["Unchanged:   Answer from the handbook.", "Removed: − Be brief.", "Added: + Be very brief."],
      { timeout: 15_000 },
    );
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // Discarding puts v2's settings back in the Draft.
    await page.getByRole("button", { name: "Discard Draft" }).click();
    await page.getByRole("button", { name: "Yes, discard the changes" }).click();
    await expect(page.getByText("Unpublished changes")).toHaveCount(0, { timeout: 15_000 });
    await expect(changes.getByText("No differences: v2 and the Draft have the same settings.")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("group", { name: "Behaviour" }).getByText("Be brief.")).toBeVisible();

    // Starting the Draft from v1 publishes nothing: v2 stays Live and the Draft now differs.
    const versions = page.getByRole("list", { name: "Versions" });
    const v1 = versions.getByRole("listitem").filter({ hasText: "First release" });
    await v1.getByRole("button", { name: "Start Draft from v1" }).click();
    await v1.getByRole("button", { name: "Yes, replace the Draft" }).click();
    await expect(page.getByText("Unpublished changes")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("Live v2")).toBeVisible();
    await expect(page.getByRole("group", { name: "Behaviour" }).getByText("Be brief.")).toHaveCount(0);
    await expect(promptChanges.getByRole("listitem")).toHaveText(["Unchanged:   Answer from the handbook.", "Removed: − Be brief."], {
      timeout: 15_000,
    });

    // Comparing v1 with v2.
    const compare = page.getByRole("region", { name: "Compare" });
    const versionIds = (await (await page.request.get(`${agentApi}/versions`)).json()) as { versions: { id: string; number: number }[] };
    const idOf = (number: number) => versionIds.versions.find((version) => version.number === number)?.id ?? "";
    await compare.getByLabel("From").selectOption(idOf(1));
    await compare.getByLabel("To").selectOption(idOf(2));
    await expect(compare.getByRole("list", { name: "Behaviour › System prompt changes" }).getByRole("listitem")).toHaveText(
      ["Unchanged:   Answer from the handbook.", "Added: + Be brief."],
      { timeout: 15_000 },
    );
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // A colleague saves the Draft; this Editor's next save is refused and they load the colleague's.
    expect((await page.request.put(`${agentApi}/draft`, { data: prompt("A colleague's prompt.") })).ok()).toBe(true);
    const temperature = page.getByRole("group", { name: "Behaviour" }).getByLabel("Temperature");
    await temperature.fill("0.2");
    const conflict = page.getByRole("alert").filter({ hasText: "Someone else saved this Draft" });
    await expect(conflict).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("status", { name: "Draft status" })).toHaveText("Not saved: someone else changed this Draft.");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    await conflict.getByRole("button", { name: "Load their changes" }).click();
    await expect(page.getByRole("group", { name: "Behaviour" }).getByText("A colleague's prompt.")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("group", { name: "Behaviour" }).getByLabel("Temperature")).toHaveValue("0.7");

    // The API agrees, and the Draft actions were audited.
    const agent = (await (await page.request.get(agentApi)).json()) as { draft: { behaviour: { system_prompt: string } } };
    expect(agent.draft.behaviour.system_prompt).toBe("A colleague's prompt.");
    const organisationId = agentApi.split("/")[3] ?? "";
    for (const action of ["agent.draft_discarded", "agent.draft_started_from_version"]) {
      const audit = await page.request.get(`/api/organisations/${organisationId}/audit-events`, { params: { action } });
      expect(((await audit.json()) as { items: unknown[] }).items).toHaveLength(1);
    }
  });
});
