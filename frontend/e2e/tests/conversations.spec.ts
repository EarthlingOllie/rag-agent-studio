import { expect, test } from "../fixtures";
import { openAgentView } from "../fixtures/agent";

// The compose stack checks keys with the fake verifier and answers with the fake gateway's
// chat model. No real provider is called and no real key is used.
const CHAT_KEY = "sk-ant-e2e-test-only-not-a-real-key-e701";

test.describe("Conversations viewer", () => {
  test("an Editor finds a Visitor's Conversation beside a flagged Playground one, filters the list and reads a reply's Trace", async ({
    signedInPage: page,
    makeAxeBuilder,
    browser,
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
    const project = await page.request.post(`${organisation}/projects`, { data: { name: "Northwind HR" } });
    const { id: projectId } = (await project.json()) as { id: string };
    const agent = await page.request.post(`${organisation}/projects/${projectId}/agents`, { data: { name: "HR helper" } });
    const { id: agentId, public_id: publicId } = (await agent.json()) as { id: string; public_id: string };
    const agentApi = `${organisation}/projects/${projectId}/agents/${agentId}`;
    expect((await page.request.post(`${agentApi}/versions`, { data: { note: "First release" } })).status()).toBe(201);

    // A Visitor (another browser, no Studio session) chats with the Live Version through the widget API.
    const visitor = await browser.newContext();
    const shell = await (await visitor.request.get(`/widget/a/${publicId}`)).text();
    const boot = JSON.parse(/<script id="widget-boot" type="application\/json">(.*?)<\/script>/.exec(shell)?.[1] ?? "{}") as {
      bootstrap_token: string;
    };
    const started = await visitor.request.post(`/api/widget/agents/${publicId}/conversations`, {
      data: { bootstrap_token: boot.bootstrap_token },
    });
    expect(started.status()).toBe(201);
    const { conversation_token: token } = (await started.json()) as { conversation_token: string };
    const asked = await visitor.request.post(`/api/widget/agents/${publicId}/messages`, {
      data: { content: "How many days of annual leave do I get?" },
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(asked.status()).toBe(200);
    await visitor.close();

    // The Editor tries the Draft in the Playground too.
    const playground = await page.request.post(`${agentApi}/playground/conversations`);
    const { id: playgroundId } = (await playground.json()) as { id: string };
    expect(
      (await page.request.post(`${agentApi}/playground/conversations/${playgroundId}/messages`, { data: { content: "Testing leave" } })).status(),
    ).toBe(200);

    // The Agent's Conversations view leads to its Conversations.
    await page.goto(`/organisations/${organisationId}/projects/${projectId}/agents/${agentId}`);
    await openAgentView(page, "Conversations");
    const list = page.getByRole("list", { name: "Conversations" });
    const playgroundRow = list.getByRole("listitem").filter({ hasText: "Testing leave" });
    const visitorRow = list.getByRole("listitem").filter({ hasText: "How many days of annual leave" });
    // Each listed Conversation's facts: when, the Agent, with whom, the Versions that answered…
    await expect(playgroundRow.getByRole("definition").nth(2)).toHaveText("Playground", { timeout: 15_000 });
    await expect(visitorRow.getByRole("definition").nth(2)).toHaveText("Visitor");
    await expect(visitorRow.getByRole("definition").nth(3)).toHaveText("v1");
    // The view is the Agent's: its list has no Agent filter.
    const filters = page.getByRole("group", { name: "Filter Conversations" });
    await expect(filters.getByLabel("Agent")).toHaveCount(0);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // Visitors only, then v1 only.
    await filters.getByRole("radio", { name: "Visitors" }).click();
    await expect(playgroundRow).toHaveCount(0);
    await filters.getByLabel("Version").selectOption("v1");
    await expect(visitorRow).toHaveCount(1);
    await expect(page).toHaveURL(/show=visitors/);

    // Open it beside the list and read the reply's Trace, folded under it.
    await visitorRow.getByRole("link", { name: "How many days of annual leave do I get?" }).click();
    await expect(page.getByRole("heading", { level: 4, name: "Conversation with HR helper" })).toBeVisible();
    await expect(page.getByText(/^Visitor Conversation · started/)).toBeVisible();
    const messages = page.getByRole("list", { name: "Messages" });
    await expect(messages.getByRole("listitem", { name: "Visitor" })).toHaveText("VisitorHow many days of annual leave do I get?");
    const reply = messages.getByRole("listitem", { name: "HR helper" });
    await expect(reply.getByLabel("Version 1")).toBeVisible();
    await reply.getByText("Trace", { exact: true }).click();
    const trace = reply.getByRole("group", { name: "Trace" });
    await expect(trace.getByText("Answered by")).toBeVisible();
    await expect(trace.getByText("Pinned by Agent Version v1")).toBeVisible();
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // The list is still beside it, still filtered.
    await expect(visitorRow).toHaveCount(1);
    await expect(playgroundRow).toHaveCount(0);
  });
});
