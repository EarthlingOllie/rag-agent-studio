import { fileURLToPath } from "node:url";

import { expect, test } from "../fixtures";
import { HOST_URL } from "../fixtures/env";
import { latestEmailTo } from "../fixtures/mailpit";

/** The seed staff handbook (synthetic content), so questions reach the model and use tokens. */
const HANDBOOK = fileURLToPath(new URL("../../../seed/documents/northwind-staff-handbook.md", import.meta.url));
// The compose stack checks keys with the fake verifier and answers with the fake gateway's
// chat model. No real provider is called and no real key is used.
const CHAT_KEY = "sk-ant-e2e-test-only-not-a-real-key-e606";
const UNAVAILABLE = "Our helper has answered all it can today. Please come back tomorrow.";
const ANSWER = "Fake reply from anthropic:claude-haiku-4-5.";

test.describe("Token Budget", () => {
  test("an Editor sets a tiny daily Token Budget; once a Visitor's reply spends it the next message gets the unavailable text, the Studio shows the alert and meter, the Owner is emailed, and the Playground still answers", async ({
    signedInPage: page,
    member,
    makeAxeBuilder,
    browser,
  }) => {
    test.setTimeout(180_000);
    await page.goto("/");
    const me = (await (await page.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
    const organisation = `/api/organisations/${me.organisations[0]?.id ?? ""}`;
    const credential = await page.request.post(`${organisation}/credentials`, {
      data: { name: "Support Claude", provider: "anthropic", api_key: CHAT_KEY },
    });
    expect(credential.status()).toBe(201);
    const { id } = (await credential.json()) as { id: string };
    expect(
      (await page.request.put(`${organisation}/default-model`, { data: { credential_id: id, model: "claude-haiku-4-5" } })).status(),
    ).toBe(200);

    // A live Agent over the handbook.
    await page.getByRole("navigation", { name: "Organisation" }).getByRole("link", { name: "Projects" }).click();
    const newProject = page.getByRole("form", { name: "New Project" });
    await newProject.getByLabel("Name").fill("Northwind Thrifty Desk");
    await newProject.getByRole("button", { name: "Create Project" }).click();
    await page.getByLabel("Choose files to upload").setInputFiles(HANDBOOK);
    const row = page.getByRole("table", { name: "Documents" }).getByRole("row", { name: /northwind-staff-handbook\.md/ });
    await expect(row.getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 60_000 });
    await page.getByRole("navigation", { name: "Project" }).getByRole("link", { name: "Agents" }).click();
    const newAgent = page.getByRole("form", { name: "New Agent" });
    await newAgent.getByLabel("Name").fill("Thrifty helper");
    await newAgent.getByRole("button", { name: "Create Agent" }).click();
    await expect(page.getByRole("heading", { level: 2, name: "Thrifty helper" })).toBeVisible({ timeout: 15_000 });
    const agentPage = page.url();
    const agentApi = agentPage.replace(/^https?:\/\/[^/]+/, "/api");
    const { public_id: publicId } = (await (await page.request.get(agentApi)).json()) as { public_id: string };
    const publish = page.getByRole("form", { name: "Publish" });
    await publish.getByRole("textbox", { name: "Note" }).fill("First release");
    await publish.getByRole("button", { name: "Publish" }).click();
    await expect(page.getByText("Live v1")).toBeVisible({ timeout: 15_000 });

    // Operational Settings: the host page's origin, the unavailable text, and a tiny budget.
    const embed = page.getByRole("region", { name: "Embed", exact: true });
    const origins = embed.getByLabel("Allowed Origins");
    await expect(origins).toBeEnabled();
    await origins.fill(new URL(HOST_URL).origin);
    await embed.getByRole("button", { name: "Save Allowed Origins" }).click();
    await expect(embed.getByText("Saved. Pages on these sites can show the Agent now.")).toBeVisible({ timeout: 15_000 });
    await embed.getByLabel("Unavailable text").fill(UNAVAILABLE);
    await embed.getByRole("button", { name: "Save unavailable text" }).click();
    await expect(embed.getByText("Saved. Visitors see it from their next message.")).toBeVisible({ timeout: 15_000 });
    const budget = embed.getByLabel("Tokens per day");
    await expect(budget).toHaveValue("1000000");
    await expect(embed.getByText("0 of 1,000,000 tokens used today (0%).")).toBeVisible();
    await budget.fill("1");
    await embed.getByRole("button", { name: "Save Token Budget" }).click();
    await expect(embed.getByText("Saved. The new budget applies to the next message.")).toBeVisible({ timeout: 15_000 });
    await expect(embed.getByText("0 of 1 tokens used today (0%).")).toBeVisible({ timeout: 15_000 });

    // A Visitor on the host page: the first reply is answered and spends the budget; the
    // next message gets the unavailable text.
    const visitor = await browser.newContext();
    const host = await visitor.newPage();
    const bodies: string[] = [];
    host.on("response", (response) => {
      if (response.url().endsWith(`/api/widget/agents/${publicId}/messages`)) {
        void response.text().then((body) => bodies.push(body));
      }
    });
    await host.goto(`${HOST_URL}/?agent=${publicId}&launcher=inline`);
    const widget = host.frameLocator('iframe[title="Chat"]');
    await expect(widget.getByRole("heading", { name: "Thrifty helper" })).toBeVisible({ timeout: 15_000 });
    const log = widget.getByRole("log", { name: "Conversation" });
    await widget.getByLabel("Message").fill("How many days of annual leave do I get?");
    await widget.getByRole("button", { name: "Send" }).click();
    await expect(log.getByRole("listitem", { name: "Thrifty helper" })).toContainText(ANSWER, { timeout: 15_000 });
    await widget.getByLabel("Message").fill("And how do I book it?");
    await widget.getByRole("button", { name: "Send" }).click();
    await expect(widget.getByRole("alert")).toHaveText(UNAVAILABLE, { timeout: 15_000 });
    await expect(log.getByRole("listitem", { name: "Thrifty helper" })).toHaveCount(1);
    await expect
      .poll(() => {
        // The last response's only event, as [name, data].
        const [event = "", data = "null"] = (bodies.at(-1) ?? "").trim().split("\n");
        return [event, JSON.parse(data.replace(/^data: /, "")) as unknown];
      })
      .toEqual(["event: unavailable", { reason: "budget_exhausted", message: UNAVAILABLE }]);
    await visitor.close();

    // The Studio: the alert badge on the Agent's page and in the Agent list, and the meter full.
    await page.reload();
    await expect(page.getByRole("heading", { level: 2, name: "Thrifty helper" })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("region", { name: "Agent", exact: true }).getByText("Budget exhausted").first()).toBeVisible();
    await expect(
      embed.getByText(
        "Today's Token Budget is spent: Visitors see the unavailable text until midnight UTC, or until you raise the budget.",
      ),
    ).toBeVisible({ timeout: 15_000 });
    await expect(embed.getByRole("progressbar", { name: "Tokens used today" })).toHaveAttribute("aria-valuenow", "1");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    await page.getByRole("link", { name: "All Agents" }).click();
    const listed = page.getByRole("list", { name: "Agents" }).getByRole("listitem").filter({ hasText: "Thrifty helper" });
    await expect(listed.getByText("Budget exhausted")).toBeVisible({ timeout: 15_000 });

    // The Owner got one email about it.
    const email = await latestEmailTo(page.request, member.email);
    expect(email.Subject).toBe("Thrifty helper has used its daily Token Budget");
    expect(email.Text).toContain("midnight UTC");

    // The Playground is exempt: it still answers.
    await page.goto(agentPage);
    const messages = page.getByRole("list", { name: "Playground messages" });
    await page.getByLabel("Question", { exact: true }).fill("How many days of annual leave do I get?");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(messages.getByRole("listitem", { name: "Thrifty helper" }).first()).toContainText(ANSWER, {
      timeout: 15_000,
    });
  });
});
