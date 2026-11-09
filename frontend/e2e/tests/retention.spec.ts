import { expect, test } from "../fixtures";
import { openSection } from "../fixtures/navigation";

// The compose stack checks keys with the fake verifier and answers with the fake gateway's
// chat model. No real provider is called and no real key is used.
const CHAT_KEY = "sk-ant-e2e-test-only-not-a-real-key-e707";

test.describe("Retention and tombstones", () => {
  test("an Owner sets the Retention Window, and the change is audited", async ({ signedInPage: page, makeAxeBuilder }) => {
    await page.goto("/");
    const me = (await (await page.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
    const organisationId = me.organisations[0]?.id ?? "";

    await page.goto(`/organisations/${organisationId}/settings`);
    const retention = page.getByRole("region", { name: "Retention" });
    await expect(retention).toContainText("kept for 90 days, then purged every night. Metrics are kept.");
    const days = retention.getByRole("spinbutton", { name: "Retention Window (days)" });
    await expect(days).toHaveValue("90");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    await days.fill("30");
    await retention.getByRole("button", { name: "Save" }).click();
    await expect(retention.getByRole("status")).toHaveText("Saved.");
    await expect(retention).toContainText("kept for 30 days");

    // The Audit tab lists the change.
    await openSection(page, "Organisation settings", "Audit");
    await expect(page.getByRole("table").getByText("organisation.retention_window_changed")).toBeVisible();
    await page.reload();
    await openSection(page, "Organisation settings", "General");
    await expect(page.getByRole("region", { name: "Retention" })).toContainText("kept for 30 days");
  });

  test("a Trace keeps a deleted Document's name as a tombstone, and an Owner deletes a Conversation on request", async ({
    signedInPage: page,
    makeAxeBuilder,
    browser,
  }) => {
    test.setTimeout(180_000);
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
    const project = await page.request.post(`${organisation}/projects`, { data: { name: "Retention HR" } });
    const { id: projectId } = (await project.json()) as { id: string };
    const projectPage = `/organisations/${organisationId}/projects/${projectId}`;

    // A leave policy Document, uploaded and Ready.
    await page.goto(projectPage);
    await page.getByLabel("Choose files to upload").setInputFiles({
      name: "leave-policy.md",
      mimeType: "text/markdown",
      buffer: Buffer.from(`# Leave\n\nEveryone gets 25 days of annual leave a year. ${String(Date.now())}\n`),
    });
    const documents = page.getByRole("table", { name: "Documents" });
    const documentRow = documents.getByRole("row", { name: /leave-policy\.md/ });
    await expect(documentRow.getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 60_000 });

    const agent = await page.request.post(`${organisation}/projects/${projectId}/agents`, { data: { name: "HR helper" } });
    const { id: agentId, public_id: publicId } = (await agent.json()) as { id: string; public_id: string };
    const agentApi = `${organisation}/projects/${projectId}/agents/${agentId}`;
    expect((await page.request.post(`${agentApi}/versions`, { data: { note: "First release" } })).status()).toBe(201);

    // A Visitor (another browser, no Studio session) asks about leave through the widget API.
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
    const bearer = { Authorization: `Bearer ${token}` };
    const asked = await visitor.request.post(`/api/widget/agents/${publicId}/messages`, {
      data: { content: "How many days of annual leave do I get?" },
      headers: bearer,
    });
    expect(asked.status()).toBe(200);

    // The Document is deleted after the answer.
    await page.goto(projectPage);
    await documentRow.getByRole("button", { name: "Delete leave-policy.md" }).click();
    await page.getByRole("group", { name: "Delete leave-policy.md?" }).getByRole("button", { name: "Delete" }).click();
    await expect(page.getByText(/No Documents yet/)).toBeVisible();

    // The reply's Trace still lists the Chunk, as a tombstone with the Document's name.
    await page.goto(`${projectPage}/conversations`);
    await page.getByRole("link", { name: "How many days of annual leave do I get?" }).click();
    const messages = page.getByRole("list", { name: "Messages" });
    const reply = messages.getByRole("listitem", { name: "HR helper" });
    await reply.getByRole("button", { name: "Trace" }).click();
    const drawer = page.getByRole("dialog", { name: "Trace" });
    const chunks = drawer.getByRole("table", { name: "Retrieved Chunks" });
    await expect(chunks.getByRole("cell", { name: "Chunk from deleted Document leave-policy.md" })).toBeVisible();
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    await drawer.getByRole("button", { name: "Close" }).click();

    // The Owner deletes the Conversation on the Visitor's request, after confirming.
    await page.getByRole("button", { name: "Delete Conversation" }).click();
    await expect(page.getByRole("group", { name: "Delete Conversation" })).toContainText("Its numbers stay in the metrics.");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    await page.getByRole("button", { name: "Yes, delete it" }).click();
    await expect(page.getByText(/^Deleted on request .* Its numbers stay in the metrics\.$/)).toBeVisible();
    await expect(messages.getByRole("listitem", { name: "Visitor" })).toContainText(
      "the Conversation was deleted on request.",
    );
    await expect(messages).not.toContainText("How many days of annual leave");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // The Visitor's Conversation token no longer works, and the deletion is audited.
    expect((await visitor.request.get(`/api/widget/agents/${publicId}/conversation`, { headers: bearer })).status()).toBe(401);
    await visitor.close();
    const audit = await page.request.get(`${organisation}/audit-events`, { params: { action: "conversation.deleted" } });
    const { items } = (await audit.json()) as { items: { target: { type: string } }[] };
    expect(items.map((item) => item.target.type)).toEqual(["conversation"]);
    await page.getByRole("link", { name: "All Conversations" }).click();
    await expect(page.getByRole("table", { name: "Conversations" }).getByRole("link", { name: "(deleted on request)" })).toBeVisible();
  });
});
