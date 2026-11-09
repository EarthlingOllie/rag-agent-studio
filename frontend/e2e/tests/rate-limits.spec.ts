import { expect, test } from "../fixtures";
import { liveVersion, openAgentView, publishAgent, saveAllowedOrigins } from "../fixtures/agent";
import { HOST_URL } from "../fixtures/env";
import { openSection } from "../fixtures/navigation";

// The compose stack checks keys with the fake verifier and answers with the fake gateway's
// chat model. No real provider is called and no real key is used.
const CHAT_KEY = "sk-ant-e2e-test-only-not-a-real-key-e605";
const UNAVAILABLE = "Lots of questions right now. Please wait a minute and ask again.";
// The Project holds no Documents, so retrieval finds nothing and the Agent gives its fallback answer.
const ANSWER = "Sorry, I don't know the answer to that.";

test.describe("Rate limits", () => {
  test("an Editor limits each Conversation to one message a minute; a Visitor's second message gets the unavailable text, and the Playground is exempt", async ({
    signedInPage: page,
    makeAxeBuilder,
    browser,
  }) => {
    test.setTimeout(150_000);
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

    // A live Agent.
    await openSection(page, "Organisation sections", "Projects");
    const newProject = page.getByRole("form", { name: "New Project" });
    await newProject.getByLabel("Name").fill("Northwind Busy Desk");
    await newProject.getByRole("button", { name: "Create Project" }).click();
    await openSection(page, "Project sections", "Agents");
    await page.getByRole("button", { name: "New Agent" }).click();
    const newAgent = page.getByRole("form", { name: "New Agent" });
    await newAgent.getByLabel("Name").fill("Busy helper");
    await newAgent.getByRole("button", { name: "Create Agent" }).click();
    await expect(page.getByRole("heading", { level: 2, name: "Busy helper" })).toBeVisible({ timeout: 15_000 });
    const agentApi = page.url().replace(/^https?:\/\/[^/]+/, "/api");
    const { public_id: publicId } = (await (await page.request.get(agentApi)).json()) as { public_id: string };
    await publishAgent(page, "First release");
    await expect(liveVersion(page, 1)).toBeVisible({ timeout: 15_000 });

    // Operational Settings: the host page's origin, the unavailable text, and the rate limits.
    await openAgentView(page, "Embed & limits");
    const embed = page.getByRole("main");
    await saveAllowedOrigins(page, [new URL(HOST_URL).origin]);
    await embed.getByLabel("Unavailable text").fill(UNAVAILABLE);
    await embed.getByRole("button", { name: "Save unavailable text" }).click();
    await expect(embed.getByText("Saved. Visitors see it from their next message.")).toBeVisible({ timeout: 15_000 });
    const perConversation = embed.getByLabel("Messages per minute per Conversation");
    await expect(perConversation).toHaveValue("10");
    await expect(embed.getByLabel("Messages per minute per IP address")).toHaveValue("30");
    await perConversation.fill("1");
    await embed.getByRole("button", { name: "Save rate limits" }).click();
    await expect(embed.getByText("Saved. Messages over a limit get the unavailable text from now on.")).toBeVisible({
      timeout: 15_000,
    });
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // A Visitor on the host page: the first message is answered, the second is over the limit.
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
    await expect(widget.getByRole("heading", { name: "Busy helper" })).toBeVisible({ timeout: 15_000 });
    const log = widget.getByRole("log", { name: "Conversation" });
    await widget.getByLabel("Message").fill("What are your opening hours?");
    await widget.getByRole("button", { name: "Send" }).click();
    await expect(log.getByRole("listitem", { name: "Busy helper" })).toContainText(ANSWER, { timeout: 15_000 });
    await widget.getByLabel("Message").fill("And at weekends?");
    await widget.getByRole("button", { name: "Send" }).click();
    await expect(widget.getByRole("alert")).toHaveText(UNAVAILABLE, { timeout: 15_000 });
    // Only the first question got an answer; the refusal was an `unavailable` event.
    await expect(log.getByRole("listitem", { name: "Busy helper" })).toHaveCount(1);
    await expect
      .poll(() => {
        // The last response's only event, as [name, data].
        const [event = "", data = "null"] = (bodies.at(-1) ?? "").trim().split("\n");
        return [event, JSON.parse(data.replace(/^data: /, "")) as unknown];
      })
      .toEqual(["event: unavailable", { reason: "rate_limited", message: UNAVAILABLE }]);
    await visitor.close();

    // The Playground has no limits: two questions in a row are both answered.
    const messages = page.getByRole("list", { name: "Playground messages" });
    for (const [index, question] of ["What are your opening hours?", "And at weekends?"].entries()) {
      await page.getByLabel("Question", { exact: true }).fill(question);
      await page.getByRole("button", { name: "Send" }).click();
      await expect(messages.getByRole("listitem", { name: "Busy helper" }).nth(index)).toContainText(ANSWER, {
        timeout: 15_000,
      });
    }
  });
});
