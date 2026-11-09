import { expect, test } from "../fixtures";

// The compose stack checks keys with the fake verifier and answers with the fake gateway's
// chat model. No real provider is called and no real key is used.
const CHAT_KEY = "sk-ant-e2e-test-only-not-a-real-key-e708";

test.describe("Organisation cost", () => {
  test("an Owner opens the Cost page from the navigation and sees each Project's and Agent's cost, the Playground in its own column", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    test.setTimeout(120_000);
    await page.goto("/");
    const me = (await (await page.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
    const organisationId = me.organisations[0]?.id ?? "";
    const organisation = `/api/organisations/${organisationId}`;
    const credential = await page.request.post(`${organisation}/credentials`, {
      data: { name: "Support Claude", provider: "anthropic", api_key: CHAT_KEY },
    });
    expect(credential.status()).toBe(201);
    const { id } = (await credential.json()) as { id: string };
    expect(
      (await page.request.put(`${organisation}/default-model`, { data: { credential_id: id, model: "claude-haiku-4-5" } })).status(),
    ).toBe(200);
    const project = await page.request.post(`${organisation}/projects`, { data: { name: "Cost HR" } });
    const { id: projectId } = (await project.json()) as { id: string };
    const created = await page.request.post(`${organisation}/projects/${projectId}/agents`, { data: { name: "Cost helper" } });
    const { id: agentId } = (await created.json()) as { id: string };
    const agentApi = `${organisation}/projects/${projectId}/agents/${agentId}`;
    const playground = await page.request.post(`${agentApi}/playground/conversations`);
    expect(playground.status()).toBe(201);
    const { id: tryId } = (await playground.json()) as { id: string };
    const tried = await page.request.post(`${agentApi}/playground/conversations/${tryId}/messages`, {
      data: { content: "Testing the Draft before Visitors see it" },
    });
    expect(tried.status()).toBe(200);
    expect(await tried.text()).toContain("event: done");

    await page.goto(`/organisations/${organisationId}/projects`);
    await page.getByRole("navigation", { name: "Organisation" }).getByRole("link", { name: "Cost" }).click();

    await expect(page.getByRole("heading", { level: 1, name: "Organisation cost" })).toBeVisible();
    const byProject = page.getByRole("table", { name: "Cost by Project" });
    await expect(byProject.getByRole("columnheader")).toHaveText(["Project", "Visitors", "Playground", "Total"]);
    await expect(byProject.getByRole("row", { name: /^Cost HR/ })).toBeVisible();
    await expect(byProject.getByRole("row", { name: /^All Projects/ })).toBeVisible();
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    await page.getByLabel("Break down by").selectOption("Agent");
    const byAgent = page.getByRole("table", { name: "Cost by Agent" });
    await expect(byAgent.getByRole("row", { name: /^Cost helper Cost HR/ })).toBeVisible();
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
  });
});
