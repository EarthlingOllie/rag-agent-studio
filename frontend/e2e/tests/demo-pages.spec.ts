import { expect, test } from "../fixtures";
import { signInAs } from "../fixtures/auth";
import { BLOCKED_HOST_URL, HOST_URL, STUDIO_URL } from "../fixtures/env";
import { openSection } from "../fixtures/navigation";

// `make seed` runs before the suite (`make e2e`): it publishes the Product FAQ and the Low-budget
// helper with the demo host's shop origin (HOST_URL) in their Allowed Origins.
const OWNER = { email: "owner@northwind.example", password: "northwind-owner-demo" };
const DEMO_ANSWER = "Demo model (canned answer, not AI)";
const BUDGET_UNAVAILABLE = "Northwind's low-budget helper has used today's budget. Please come back tomorrow.";

interface DemoAgents {
  widget_url: string;
  shop: { public_id: string; name: string };
  budget: { public_id: string; name: string; daily_token_budget: number };
}

test.describe("Demo host pages", () => {
  test("the shop page on the allowed origin shows the Product FAQ as a bubble, and a Visitor chats with it", async ({
    page,
    makeAxeBuilder,
  }) => {
    test.setTimeout(90_000);
    await page.goto(`${HOST_URL}/demo/`);
    await expect(page.getByRole("heading", { level: 1, name: "Fine foods from small producers" })).toBeVisible();

    const widget = page.frameLocator('iframe[title="Chat"]');
    await widget.getByRole("button", { name: "Open chat" }).click({ timeout: 15_000 });
    await expect(widget.getByRole("heading", { name: "Product FAQ" })).toBeVisible({ timeout: 15_000 });
    await widget.getByLabel("Message").fill("Can I return a jar of honey?");
    await widget.getByRole("button", { name: "Send" }).click();
    const log = widget.getByRole("log", { name: "Conversation" });
    await expect(log.getByRole("listitem", { name: "Product FAQ", exact: true })).toContainText(DEMO_ANSWER, { timeout: 30_000 });
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
  });

  test("the help-centre page shows the same Agent inline", async ({ page, makeAxeBuilder }) => {
    await page.goto(`${HOST_URL}/demo/inline.html`);

    const frame = page.getByRole("region", { name: "Ask our helper" }).locator('iframe[title="Chat"]');
    await expect(frame).toBeVisible({ timeout: 15_000 });
    const widget = page.frameLocator('iframe[title="Chat"]');
    await expect(widget.getByRole("heading", { name: "Product FAQ" })).toBeVisible({ timeout: 15_000 });
    await expect(widget.getByRole("button", { name: "Open chat" })).toHaveCount(0);
    await expect(widget.getByLabel("Message")).toBeVisible();
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
  });

  test("a page on a disallowed origin pastes the same snippet, and the browser refuses to show the widget", async ({
    page,
    makeAxeBuilder,
  }) => {
    const demo = (await (await page.request.get(`${HOST_URL}/api/demo/agents`)).json()) as DemoAgents;
    const shell = await page.request.get(`${STUDIO_URL}/widget/a/${demo.shop.public_id}`);
    expect(shell.headers()["content-security-policy"]).toBe(`frame-ancestors ${new URL(HOST_URL).origin}`);

    await page.goto(`${BLOCKED_HOST_URL}/`);
    await expect(page.getByRole("heading", { level: 1, name: "This site may not show the chat" })).toBeVisible();
    await expect(page.getByText(new URL(BLOCKED_HOST_URL).origin, { exact: true })).toBeVisible();
    const iframe = page.locator('iframe[title="Chat"]');
    await expect(iframe).toHaveAttribute("src", new RegExp(`/widget/a/${demo.shop.public_id}\\?`), { timeout: 15_000 });
    // Chromium replaces a frame its frame-ancestors policy refuses with its own error page.
    await expect
      .poll(async () => (await (await iframe.elementHandle()).contentFrame())?.url(), { timeout: 15_000 })
      .toBe("chrome-error://chromewebdata/");
    await expect(page.frameLocator('iframe[title="Chat"]').getByRole("heading", { name: "Product FAQ" })).toHaveCount(0);
    expect((await makeAxeBuilder().exclude('iframe[title="Chat"]').analyze()).violations).toEqual([]);
  });

  test("one click spends the Low-budget helper's Token Budget: the widget shows its unavailable text and the Studio its alert", async ({
    page,
    browser,
    makeAxeBuilder,
  }) => {
    test.setTimeout(90_000);
    await page.goto(`${HOST_URL}/demo/budget.html`);
    const widget = page.frameLocator('iframe[title="Chat"]');
    await expect(widget.getByRole("heading", { name: "Low-budget helper" })).toBeVisible({ timeout: 15_000 });
    const status = page.getByRole("status");
    await expect(status).toHaveText("The Low-budget helper can use 2,000 tokens a day.");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    await page.getByRole("button", { name: "Use up today's Token Budget" }).click();
    await expect(status).toHaveText(
      "Today's Token Budget is spent: 2,000 of 2,000 tokens used. Send a message to see what Visitors are told.",
    );
    await widget.getByLabel("Message").fill("Do you sell honey?");
    await widget.getByRole("button", { name: "Send" }).click();
    await expect(widget.getByRole("alert")).toHaveText(BUDGET_UNAVAILABLE, { timeout: 15_000 });

    // The Studio: the demo Owner sees the alert on the Agent.
    const studio = await (await browser.newContext()).newPage();
    await signInAs(studio, OWNER);
    await studio.goto("/");
    await openSection(studio, "Organisation sections", "Projects");
    await studio.getByRole("link", { name: "Northwind Handbook" }).click();
    await openSection(studio, "Project sections", "Agents");
    const listed = studio.getByRole("list", { name: "Agents" }).getByRole("listitem").filter({ hasText: "Low-budget helper" });
    await expect(listed.getByText("Budget spent")).toBeVisible({ timeout: 15_000 });
    await studio.context().close();
  });
});
