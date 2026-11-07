import { expect, test } from "../fixtures";
import { HOST_URL } from "../fixtures/env";

const UNAVAILABLE = "Our helper is having a break. Call us on 0123 456 789.";

test.describe("Operational Settings", () => {
  test("an Editor allows only the host page's origin and words the unavailable text; a page on another origin can't frame the widget", async ({
    signedInPage: page,
    makeAxeBuilder,
    browser,
  }) => {
    test.setTimeout(120_000);
    await page.goto("/");
    const me = (await (await page.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
    const organisation = `/api/organisations/${me.organisations[0]?.id ?? ""}`;

    // A live Agent. The Organisation has no Default Model, so the Agent can't answer.
    await page.getByRole("navigation", { name: "Organisation" }).getByRole("link", { name: "Projects" }).click();
    const newProject = page.getByRole("form", { name: "New Project" });
    await newProject.getByLabel("Name").fill("Northwind Support");
    await newProject.getByRole("button", { name: "Create Project" }).click();
    await page.getByRole("navigation", { name: "Project" }).getByRole("link", { name: "Agents" }).click();
    const newAgent = page.getByRole("form", { name: "New Agent" });
    await newAgent.getByLabel("Name").fill("Support helper");
    await newAgent.getByRole("button", { name: "Create Agent" }).click();
    await expect(page.getByRole("heading", { level: 2, name: "Support helper" })).toBeVisible({ timeout: 15_000 });
    const agentApi = page.url().replace(/^https?:\/\/[^/]+/, "/api");
    const { id: agentId, public_id: publicId } = (await (await page.request.get(agentApi)).json()) as {
      id: string;
      public_id: string;
    };
    const publish = page.getByRole("form", { name: "Publish" });
    await publish.getByRole("textbox", { name: "Note" }).fill("First release");
    await publish.getByRole("button", { name: "Publish" }).click();
    await expect(page.getByText("Live v1")).toBeVisible({ timeout: 15_000 });

    // The Operational Settings, saved without publishing again.
    const allowed = new URL(HOST_URL);
    const disallowed = new URL(HOST_URL);
    disallowed.hostname = "127.0.0.1"; // The same page, served on another origin.
    const embed = page.getByRole("region", { name: "Embed", exact: true });
    const origins = embed.getByLabel("Allowed Origins");
    await expect(origins).toBeEnabled();
    await origins.fill("www.example.com");
    await embed.getByRole("button", { name: "Save Allowed Origins" }).click();
    await expect(embed.getByRole("alert")).toContainText("'www.example.com' isn't a site address.");
    await origins.fill(`${allowed.origin}\nhttps://*.example.com`);
    await embed.getByRole("button", { name: "Save Allowed Origins" }).click();
    await expect(embed.getByText("Saved. Pages on these sites can show the Agent now.")).toBeVisible({ timeout: 15_000 });
    await embed.getByLabel("Unavailable text").fill(UNAVAILABLE);
    await embed.getByRole("button", { name: "Save unavailable text" }).click();
    await expect(embed.getByText("Saved. Visitors see it from their next message.")).toBeVisible({ timeout: 15_000 });
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    // Still v1: nothing was published.
    const after = (await (await page.request.get(agentApi)).json()) as { live_version: { number: number } };
    expect(after.live_version.number).toBe(1);

    const shell = await page.request.get(`/widget/a/${publicId}`);
    expect(shell.headers()["content-security-policy"]).toBe(`frame-ancestors ${allowed.origin} https://*.example.com`);

    // Both changes are Audit Events with their before and after values.
    const audit = await page.request.get(`${organisation}/audit-events`, {
      params: { action: "agent.operational_settings_changed" },
    });
    const events = ((await audit.json()) as { items: { target: unknown; before: unknown; after: unknown }[] }).items;
    expect(events.map(({ target, before, after }) => ({ target, before, after }))).toEqual([
      {
        target: { type: "agent", id: agentId },
        before: { unavailable_text: "This assistant is temporarily unavailable. Please try again later." },
        after: { unavailable_text: UNAVAILABLE },
      },
      {
        target: { type: "agent", id: agentId },
        before: { allowed_origins: [] },
        after: { allowed_origins: [allowed.origin, "https://*.example.com"] },
      },
    ]);

    // A Visitor on the allowed origin sees the widget, and the Agent's unavailable text.
    const visitor = await browser.newContext();
    const host = await visitor.newPage();
    await host.goto(`${allowed.origin}/?agent=${publicId}`);
    const widget = host.frameLocator('iframe[title="Chat"]');
    await expect(widget.getByRole("heading", { name: "Support helper" })).toBeVisible({ timeout: 15_000 });
    await widget.getByLabel("Message").fill("Are you there?");
    await widget.getByRole("button", { name: "Send" }).click();
    await expect(widget.getByText(UNAVAILABLE)).toBeVisible({ timeout: 15_000 });

    // The same page on a disallowed origin: the browser loads the shell but refuses to show it.
    const elsewhere = await visitor.newPage();
    const refusals: string[] = [];
    elsewhere.on("console", (message) => {
      if (message.text().includes("frame-ancestors")) refusals.push(message.text());
    });
    const shellLoaded = elsewhere.waitForResponse((response) => response.url().endsWith(`/widget/a/${publicId}`));
    await elsewhere.goto(`${disallowed.origin}/?agent=${publicId}`);
    await expect(elsewhere.getByRole("heading", { name: "Northwind Traders" })).toBeVisible();
    expect((await shellLoaded).status()).toBe(200);
    await expect(elsewhere.locator('iframe[title="Chat"]')).toHaveCount(1);
    // Chrome reports the refusal: "Framing '<shell>' violates the following Content Security Policy
    // directive: "frame-ancestors <Allowed Origins>". The request has been blocked."
    await expect
      .poll(() => refusals, { timeout: 15_000 })
      .toEqual([
        expect.stringMatching(
          new RegExp(`frame-ancestors ${allowed.origin} https://\\*\\.example\\.com.*The request has been blocked`, "s"),
        ),
      ]);
    await expect(elsewhere.frameLocator('iframe[title="Chat"]').getByRole("heading", { name: "Support helper" })).toHaveCount(0);
    await expect(elsewhere.frameLocator('iframe[title="Chat"]').getByLabel("Message")).toHaveCount(0);
    await visitor.close();
  });
});
