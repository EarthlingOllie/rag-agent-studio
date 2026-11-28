import { fileURLToPath } from "node:url";

import type { Browser, Locator, Page } from "@playwright/test";

import { expect, test } from "../fixtures";
import { newMember, signUp } from "../fixtures/auth";
import { agentTabs, currentSection, menuButton, openSection, sectionNames, sidebar } from "../fixtures/navigation";
import { APPEARANCES } from "../fixtures/pages";

// The compose stack checks keys with the fake verifier and answers with the fake gateway's
// chat model. No real provider is called and no real key is used.
const CHAT_KEY = "sk-ant-e2e-test-only-not-a-real-key-p6nv";
/** The seed staff handbook (synthetic content), uploaded as an Editor would. */
const HANDBOOK = fileURLToPath(new URL("../../../seed/documents/northwind-staff-handbook.md", import.meta.url));

/** Today, as the Cost page's UTC days name it. */
const TODAY = new Date().toISOString().slice(0, 10);
/** The UTC day `days` before today. */
const DAYS_AGO = (days: number) => new Date(Date.now() - days * 86_400_000).toISOString().slice(0, 10);

async function organisationOf(page: Page): Promise<{ organisationId: string; organisation: string }> {
  const me = (await (await page.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
  const organisationId = me.organisations[0]?.id ?? "";
  return { organisationId, organisation: `/api/organisations/${organisationId}` };
}

async function createProject(page: Page, organisation: string, name: string): Promise<string> {
  const project = await page.request.post(`${organisation}/projects`, { data: { name } });
  expect(project.status()).toBe(201);
  return ((await project.json()) as { id: string }).id;
}

async function createAgent(page: Page, organisation: string, projectId: string, name: string): Promise<string> {
  const agent = await page.request.post(`${organisation}/projects/${projectId}/agents`, { data: { name } });
  expect(agent.status()).toBe(201);
  return ((await agent.json()) as { id: string }).id;
}

/** Gives the Organisation a default chat model, so the Playground answers. */
async function addChatModel(page: Page, organisation: string) {
  const credential = await page.request.post(`${organisation}/credentials`, {
    data: { name: "Support Claude", provider: "anthropic", api_key: CHAT_KEY },
  });
  expect(credential.status()).toBe(201);
  const { id } = (await credential.json()) as { id: string };
  expect(
    (await page.request.put(`${organisation}/default-model`, { data: { credential_id: id, model: "claude-haiku-4-5" } })).status(),
  ).toBe(200);
}

/** Tries the Agent's Draft once in the Playground, which costs something; returns the Conversation's id. */
async function tryInPlayground(page: Page, agentApi: string): Promise<string> {
  const playground = await page.request.post(`${agentApi}/playground/conversations`);
  expect(playground.status()).toBe(201);
  const { id } = (await playground.json()) as { id: string };
  const tried = await page.request.post(`${agentApi}/playground/conversations/${id}/messages`, {
    data: { content: "Testing the Draft before Visitors see it" },
  });
  expect(tried.status()).toBe(200);
  expect(await tried.text()).toContain("event: done");
  return id;
}

/** An Organisation that has spent something: a Project, an Agent and one Playground reply. */
async function organisationWithSpend(page: Page, prefix: string) {
  await page.goto("/");
  const { organisationId, organisation } = await organisationOf(page);
  await addChatModel(page, organisation);
  const projectId = await createProject(page, organisation, `${prefix} HR`);
  const agentId = await createAgent(page, organisation, projectId, `${prefix} helper`);
  const agentApi = `${organisation}/projects/${projectId}/agents/${agentId}`;
  await tryInPlayground(page, agentApi);
  return { organisationId, organisation, projectId, agentId, agentApi };
}

/** Adds a new Editor to the Owner's Organisation through an Invite Link, signed in in their own browser. */
async function newEditor(owner: Page, browser: Browser): Promise<Page> {
  const person = newMember({ name: "P6 Editor" });
  const { organisation } = await organisationOf(owner);
  const invited = await owner.request.post(`${organisation}/invites`, {
    data: { email: person.email, role: "editor", send_email: false },
  });
  expect(invited.status()).toBe(201);
  const token = new URL(((await invited.json()) as { link: string }).link).searchParams.get("token") ?? "";
  const page = await (await browser.newContext()).newPage();
  const joined = await page.request.post("/api/invites/sign-up", {
    data: { token, name: person.name, password: person.password },
  });
  expect(joined.status()).toBe(201);
  return page;
}

function costTable(page: Page, by: "Project" | "Agent" = "Project"): Locator {
  return page.getByRole("table", { name: `Cost by ${by}` });
}

/** The line under the filters naming the period's days. */
function period(page: Page): Locator {
  return page.getByText(/^\d{4}-\d{2}-\d{2} to \d{4}-\d{2}-\d{2} \(UTC days\)/);
}

/** How a date filter is drawn, to compare filters across pages. */
async function filterLook(input: Locator) {
  return input.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      height: style.height,
      borderRadius: style.borderTopLeftRadius,
      borderColor: style.borderTopColor,
      background: style.backgroundColor,
      fontSize: style.fontSize,
      paddingLeft: style.paddingLeft,
    };
  });
}

/** Whether focus is now inside `container`. */
async function holdsFocus(container: Locator): Promise<boolean> {
  return container.evaluate((element) => element.contains(document.activeElement));
}

test.describe("Organisation cost, navigation and accessibility", () => {
  // [12.32] [12.29]
  test("an Owner whose Organisation has spent nothing sees a designed empty state and the period it covers, not an empty table", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    await page.goto("/");
    await openSection(page, "Organisation sections", "Cost");
    await expect(page.getByRole("heading", { level: 1, name: "Organisation cost" })).toBeVisible();

    await expect(page.getByRole("heading", { name: "Nothing was spent in this period" })).toBeVisible();
    await expect(page.getByText(/Visitors' Conversations and Calls, Playground testing and Evaluation Runs in any Project show up here/)).toBeVisible();
    await expect(costTable(page)).toHaveCount(0);
    await expect(page.getByRole("list", { name: "Spend for the period" })).toHaveCount(0);
    // The default period runs up to today, and says so.
    await expect(period(page)).toContainText(` to ${TODAY} (UTC days), including today so far`);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
  });

  // [12.28] [12.29]
  test("an Owner narrows the cost with From and To date filters styled like Analytics' and Conversations', and the period under them follows", async ({
    signedInPage: page,
  }) => {
    test.setTimeout(120_000);
    const { organisationId, projectId } = await organisationWithSpend(page, "Filters");

    // The same filters on Conversations and Analytics, for comparison.
    await page.goto(`/organisations/${organisationId}/projects/${projectId}/conversations`);
    const conversationsFrom = await filterLook(page.getByLabel("From (UTC)"));
    await page.goto(`/organisations/${organisationId}/projects/${projectId}/analytics`);
    await expect(page.getByLabel("From (UTC)")).toBeVisible({ timeout: 15_000 });
    const analyticsFrom = await filterLook(page.getByLabel("From (UTC)"));
    expect(analyticsFrom).toEqual(conversationsFrom);

    await page.goto(`/organisations/${organisationId}/cost`);
    const from = page.getByLabel("From (UTC)");
    const to = page.getByLabel("To (UTC)");
    await expect(costTable(page).getByRole("row", { name: /^Filters HR/ })).toBeVisible({ timeout: 15_000 });
    expect(await filterLook(from)).toEqual(analyticsFrom);
    expect(await filterLook(to)).toEqual(analyticsFrom);

    // A past month: nothing was spent then, and the period names exactly those days.
    await from.fill("2024-01-01");
    await to.fill("2024-01-31");
    await expect(period(page)).toHaveText(/^2024-01-01 to 2024-01-31 \(UTC days\)/);
    await expect(page.getByRole("heading", { name: "Nothing was spent in this period" })).toBeVisible();
    await expect(costTable(page)).toHaveCount(0);

    // The period sits under the filters.
    const filters = await page.getByRole("group", { name: "Choose what to show" }).boundingBox();
    const line = await period(page).boundingBox();
    expect(line?.y ?? 0).toBeGreaterThanOrEqual((filters?.y ?? 0) + (filters?.height ?? 0));

    // The last two weeks, up to today: the Playground reply is back.
    await from.fill(DAYS_AGO(14));
    await to.fill(TODAY);
    await expect(period(page)).toHaveText(new RegExp(`^${DAYS_AGO(14)} to ${TODAY} \\(UTC days\\)`));
    await expect(costTable(page).getByRole("row", { name: /^Filters HR/ })).toBeVisible();

    // Cleared, the filters fall back to the default period, which ends today.
    await from.fill("");
    await to.fill("");
    await expect(period(page)).toContainText(` to ${TODAY} (UTC days)`);
    await expect(period(page)).not.toContainText(DAYS_AGO(14));
  });

  // [12.33]
  test("an Owner who picks From after To, or more than 366 days, is told what is wrong with the dates and can correct them", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    await page.goto("/");
    await openSection(page, "Organisation sections", "Cost");
    const from = page.getByLabel("From (UTC)");
    const to = page.getByLabel("To (UTC)");
    const notice = page.getByRole("alert").filter({ hasText: "Check the dates" });
    const message = "Check the dates: From can't be after To, and the period can be at most 366 days.";

    await from.fill("2025-03-10");
    await to.fill("2025-03-01");
    // The page retries the refused request a few times before it explains, so allow for that.
    await expect(notice).toHaveText(message, { timeout: 20_000 });
    await expect(period(page)).toHaveCount(0);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    await from.fill("2024-01-01");
    await to.fill("2025-06-01");
    await expect(notice).toHaveText(message, { timeout: 20_000 });

    // A valid period clears the notice.
    await to.fill("2024-06-01");
    await expect(notice).toHaveCount(0);
    await expect(period(page)).toHaveText(/^2024-01-01 to 2024-06-01 \(UTC days\)/);
  });

  // [12.30]
  test("an Owner compares spend in right-aligned mono amounts, with the All Projects total row set apart", async ({ signedInPage: page }) => {
    test.setTimeout(120_000);
    const { organisationId } = await organisationWithSpend(page, "Amounts");
    await page.goto(`/organisations/${organisationId}/cost`);
    const table = costTable(page);
    const row = table.getByRole("row", { name: /^Amounts HR/ });
    await expect(row).toBeVisible({ timeout: 15_000 });

    const look = (cell: Locator) =>
      cell.evaluate((element) => {
        const style = getComputedStyle(element);
        const row = getComputedStyle(element.parentElement as Element);
        return {
          align: style.textAlign,
          font: style.fontFamily,
          weight: Number(style.fontWeight),
          rowBackground: row.backgroundColor,
          rowBorderTop: row.borderTopWidth,
        };
      });
    const bodyFont = await page.locator("body").evaluate((element) => getComputedStyle(element).fontFamily);
    const amount = await look(row.getByRole("cell").last());
    expect(amount.align).toBe("right");
    expect(amount.font).toMatch(/mono/i);
    expect(amount.font).not.toBe(bodyFont);
    // Every amount column reads like money.
    await expect(row.getByRole("cell")).toHaveText([/^\$\d/, /^\$\d/, /^\$\d/, /^\$\d/, /^\$\d/]);

    const total = table.getByRole("row", { name: /^All Projects/ });
    await expect(total).toBeVisible();
    const totalAmount = await look(total.getByRole("cell").last());
    expect(totalAmount.align).toBe("right");
    expect(totalAmount.font).toMatch(/mono/i);
    // Set apart: its own background and a rule above it, heavier type, and last in the table.
    expect(totalAmount.rowBackground).not.toBe(amount.rowBackground);
    expect(totalAmount.rowBorderTop).not.toBe("0px");
    expect(totalAmount.weight).toBeGreaterThan(amount.weight);
    await expect(table.getByRole("row").last()).toHaveAccessibleName(/^All Projects/);
    const headerAlign = await table.getByRole("columnheader", { name: "Total" }).evaluate((element) => getComputedStyle(element).textAlign);
    expect(headerAlign).toBe("right");
  });

  // [12.35]
  test("on a phone the cost table scrolls sideways inside its card while the page itself does not", async ({ signedInPage: page }) => {
    test.setTimeout(120_000);
    const { organisationId } = await organisationWithSpend(page, "Phone");
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`/organisations/${organisationId}/cost`);
    await page.getByRole("radiogroup", { name: "Break down by" }).getByRole("radio", { name: "Agent" }).click();
    await expect(costTable(page, "Agent").getByRole("row", { name: /^Phone helper/ })).toBeVisible({ timeout: 15_000 });

    const card = page.getByRole("region", { name: "Cost by Agent" });
    const sizes = await card.evaluate((element) => ({
      scroll: element.scrollWidth,
      client: element.clientWidth,
      overflow: getComputedStyle(element).overflowX,
    }));
    expect(sizes.overflow).toBe("auto");
    expect(sizes.scroll).toBeGreaterThan(sizes.client);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    const box = await card.boundingBox();
    expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(390);

    // It scrolls with the keyboard too: the card takes focus.
    await card.focus();
    await page.keyboard.press("ArrowRight");
    await page.keyboard.press("End");
    await expect.poll(() => card.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);
    expect(await page.evaluate(() => window.scrollX)).toBe(0);
  });

  // [12.63]
  test("an Editor's sidebar leaves out Cost, which an Owner's offers", async ({ signedInPage: owner, browser, makeAxeBuilder }) => {
    await owner.goto("/");
    expect(await sectionNames(owner, "Organisation sections")).toEqual(["Projects", "Cost", "Settings"]);

    const editor = await newEditor(owner, browser);
    await editor.goto("/");
    await expect(editor.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible();
    expect(await sectionNames(editor, "Organisation sections")).toEqual(["Projects", "Settings"]);
    await expect(sidebar(editor).getByRole("link", { name: "Cost", exact: true })).toHaveCount(0);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    await editor.context().close();
  });

  // [12.34]
  test("an Editor who opens Cost by its address is told that only Owners see the Organisation's spend", async ({
    signedInPage: owner,
    browser,
  }) => {
    test.setTimeout(120_000);
    const { organisationId, organisation } = await organisationWithSpend(owner, "Editor view");
    const editor = await newEditor(owner, browser);
    await editor.goto(`/organisations/${organisationId}/cost`);

    await expect(editor.getByRole("heading", { level: 1, name: "Organisation cost" })).toBeVisible();
    await expect(editor.getByRole("heading", { name: "Only Owners see the Organisation's spend" })).toBeVisible();
    await expect(editor.getByText("Ask an Owner of this Organisation if you need to know what it spent.")).toBeVisible();
    // Nothing of the spend, nor the filters, is shown, and the API refuses it.
    await expect(costTable(editor)).toHaveCount(0);
    await expect(editor.getByLabel("From (UTC)")).toHaveCount(0);
    await expect(editor.getByText(/\$\d/)).toHaveCount(0);
    expect((await editor.request.get(`${organisation}/cost`)).status()).toBe(403);
    expect(await currentSection(editor, "Organisation sections")).toBe("");
    await editor.context().close();
  });

  // [12.64]
  test("a Member inside a Project jumps to another Project from the switcher on the Project's name in the sidebar", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    await page.goto("/");
    const { organisationId, organisation } = await organisationOf(page);
    const firstId = await createProject(page, organisation, "Payroll desk");
    const secondId = await createProject(page, organisation, "Onboarding desk");

    await page.goto(`/organisations/${organisationId}/projects/${firstId}`);
    await expect(page.getByRole("heading", { level: 1, name: "Payroll desk" })).toBeVisible();
    await expect(menuButton(page, "Projects")).toHaveAccessibleName("Payroll desk, Projects");
    const offered = await sectionNames(page, "Projects");
    expect(offered).toContain("Payroll desk");
    expect(offered).toContain("Onboarding desk");
    expect(offered.at(-1)).toBe("All Projects");

    // The open Project is marked in the menu.
    await menuButton(page, "Projects").click();
    const menu = page.getByRole("menu", { name: "Projects" });
    await expect(menu.getByRole("menuitem", { name: "Payroll desk" })).toHaveAttribute("aria-current", "page");
    await expect(menu.getByRole("menuitem", { name: "Onboarding desk" })).not.toHaveAttribute("aria-current", "page");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    await menu.getByRole("menuitem", { name: "Onboarding desk" }).click();

    await expect(page).toHaveURL(new RegExp(`/projects/${secondId}$`));
    await expect(page.getByRole("heading", { level: 1, name: "Onboarding desk" })).toBeVisible();
    await expect(menuButton(page, "Projects")).toHaveAccessibleName("Onboarding desk, Projects");
    expect(await currentSection(page, "Project sections")).toBe("Documents");
  });

  // [12.66]
  test("a Member on a Document or a Conversation keeps its section highlighted in the sidebar", async ({ signedInPage: page }) => {
    test.setTimeout(180_000);
    await page.goto("/");
    const { organisationId, organisation } = await organisationOf(page);
    await addChatModel(page, organisation);
    const projectId = await createProject(page, organisation, "Highlight HR");
    const agentId = await createAgent(page, organisation, projectId, "Highlight helper");
    const agentApi = `${organisation}/projects/${projectId}/agents/${agentId}`;
    const conversationId = await tryInPlayground(page, agentApi);
    const project = `/organisations/${organisationId}/projects/${projectId}`;

    // A Document, uploaded as an Editor would.
    await page.goto(project);
    await page.getByLabel("Upload", { exact: true }).setInputFiles(HANDBOOK);
    const documentLink = page.getByRole("table", { name: "Documents" }).getByRole("link", { name: "northwind-staff-handbook.md" });
    await expect(documentLink).toBeVisible({ timeout: 15_000 });
    await documentLink.click();
    await expect(page).toHaveURL(/\/documents\/[0-9a-f-]+$/);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 15_000 });
    expect(await currentSection(page, "Project sections")).toBe("Documents");

    // A Conversation, opened from the Project's Conversations.
    await page.goto(`${project}/conversations/${conversationId}`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 15_000 });
    expect(await currentSection(page, "Project sections")).toBe("Conversations");

    // The same Conversation, opened inside its Agent, is still under Agents.
    await page.goto(`${project}/agents/${agentId}/conversations/${conversationId}`);
    await expect(page.getByRole("heading", { level: 1, name: "Highlight helper" })).toBeVisible({ timeout: 15_000 });
    expect(await currentSection(page, "Project sections")).toBe("Agents");
  });

  // [12.73]
  test("a Member on an Agent switches to another Agent from the ▾ on its name, without going back to the list", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    await page.goto("/");
    const { organisationId, organisation } = await organisationOf(page);
    const projectId = await createProject(page, organisation, "Switch HR");
    const firstId = await createAgent(page, organisation, projectId, "Leave helper");
    const secondId = await createAgent(page, organisation, projectId, "Payslip helper");

    await page.goto(`/organisations/${organisationId}/projects/${projectId}/agents/${firstId}/versions`);
    await expect(page.getByRole("heading", { level: 1, name: "Leave helper" })).toBeVisible();
    const switcher = menuButton(page, "Agents");
    await expect(switcher).toHaveAccessibleName("Leave helper, Agents");
    await switcher.click();
    const menu = page.getByRole("menu", { name: "Agents" });
    await expect(menu.getByRole("menuitem")).toHaveText(["Leave helper", "Payslip helper"]);
    await expect(menu.getByRole("menuitem", { name: "Leave helper" })).toHaveAttribute("aria-current", "page");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    await menu.getByRole("menuitem", { name: "Payslip helper" }).click();

    // The other Agent opens on its Playground.
    await expect(page).toHaveURL(new RegExp(`/agents/${secondId}$`));
    await expect(page.getByRole("heading", { level: 1, name: "Payslip helper" })).toBeVisible();
    await expect(menuButton(page, "Agents")).toHaveAccessibleName("Payslip helper, Agents");
    expect(await currentSection(page, "Agent views")).toBe("Playground");
    expect(await currentSection(page, "Project sections")).toBe("Agents");
  });

  // [11.7]
  test("a Member moves sideways between Organisations, Projects, sections and Agents from the switchers without going back up", async ({
    signedInPage: page,
    member,
    browser,
  }) => {
    // A second Organisation the Member belongs to, as an Editor.
    const otherOwner = newMember({ organisationName: `P6 Sideways ${member.name.slice(-8)}` });
    const other = await browser.newContext();
    await signUp(other.request, otherOwner);
    const otherMe = (await (await other.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
    const secondOrganisationId = otherMe.organisations[0]?.id ?? "";
    const invited = await other.request.post(`/api/organisations/${secondOrganisationId}/invites`, {
      data: { email: member.email, role: "editor", send_email: false },
    });
    expect(invited.status()).toBe(201);
    const token = new URL(((await invited.json()) as { link: string }).link).searchParams.get("token") ?? "";
    expect((await page.request.post("/api/invites/accept", { data: { token } })).status()).toBe(200);
    await other.close();

    await page.goto("/");
    const { organisationId, organisation } = await organisationOf(page);
    const firstProject = await createProject(page, organisation, "Sideways HR");
    await createProject(page, organisation, "Sideways IT");
    const firstAgent = await createAgent(page, organisation, firstProject, "Sideways leave");
    await createAgent(page, organisation, firstProject, "Sideways payslips");

    // Deep inside an Agent's view.
    await page.goto(`/organisations/${organisationId}/projects/${firstProject}/agents/${firstAgent}/versions`);
    await expect(page.getByRole("heading", { level: 1, name: "Sideways leave" })).toBeVisible();

    // Agent → Agent.
    await openSection(page, "Agents", "Sideways payslips");
    await expect(page.getByRole("heading", { level: 1, name: "Sideways payslips" })).toBeVisible();
    // Section → section.
    await openSection(page, "Project sections", "Analytics");
    expect(await currentSection(page, "Project sections")).toBe("Analytics");
    // Project → Project.
    await openSection(page, "Projects", "Sideways IT");
    await expect(page.getByRole("heading", { level: 1, name: "Sideways IT" })).toBeVisible();
    expect(await currentSection(page, "Projects")).toBe("Sideways IT");
    // Organisation → Organisation.
    await openSection(page, "Organisations", otherOwner.organisationName);
    await expect(page).toHaveURL(new RegExp(`/organisations/${secondOrganisationId}/projects$`));
    expect(await currentSection(page, "Organisations")).toBe(otherOwner.organisationName);
  });

  // [12.75] [12.82]
  test("a screen-reader user hears the Agent's views as a row with the selected one marked, Conversations staying selected on an Agent's Conversation", async ({
    signedInPage: page,
  }) => {
    test.setTimeout(120_000);
    const { organisationId, projectId, agentId, agentApi } = await organisationWithSpend(page, "Views");
    const conversationId = await tryInPlayground(page, agentApi);
    const agentPath = `/organisations/${organisationId}/projects/${projectId}/agents/${agentId}`;

    await page.goto(agentPath);
    await expect(page.getByRole("heading", { level: 1, name: "Views helper" })).toBeVisible();
    const views = agentTabs(page);
    expect(await sectionNames(page, "Agent views")).toEqual(["Playground", "Versions", "Evaluation", "Embed & limits", "Conversations"]);

    // Exactly one view is marked selected, and it follows the Member.
    for (const view of ["Playground", "Versions", "Evaluation", "Embed & limits", "Conversations"]) {
      if (view !== "Playground") await openSection(page, "Agent views", view);
      await expect(views.getByRole("link", { name: view, exact: true })).toHaveAttribute("aria-current", "page");
      await expect(views.locator("a[aria-current=page]")).toHaveCount(1);
    }

    // [12.75] One of the Agent's Conversations, opened from its Conversations: the tab stays selected.
    await page.goto(`${agentPath}/conversations/${conversationId}`);
    await expect(page.getByRole("heading", { level: 1, name: "Views helper" })).toBeVisible({ timeout: 15_000 });
    await expect(views.getByRole("link", { name: "Conversations", exact: true })).toHaveAttribute("aria-current", "page");
    await expect(views.locator("a[aria-current=page]")).toHaveCount(1);
    expect(await currentSection(page, "Agent views")).toBe("Conversations");
  });

  // [11.32]
  test("a keyboard user opens, moves through and leaves the switchers and menus, which announce themselves", async ({ signedInPage: page }) => {
    await page.goto("/");
    const { organisationId, organisation } = await organisationOf(page);
    const projectId = await createProject(page, organisation, "Keys HR");
    await createProject(page, organisation, "Keys IT");
    const agentId = await createAgent(page, organisation, projectId, "Keys helper");
    await createAgent(page, organisation, projectId, "Keys other");

    await page.goto(`/organisations/${organisationId}/projects/${projectId}/agents/${agentId}/versions`);
    await expect(page.getByRole("heading", { level: 1, name: "Keys helper" })).toBeVisible();

    for (const switcher of ["Projects", "Agents", "Account"] as const) {
      const button = menuButton(page, switcher);
      await expect(button).toHaveAttribute("aria-haspopup", "menu");
      await expect(button).toHaveAttribute("aria-expanded", "false");
      await button.focus();
      await page.keyboard.press("Enter");
      const menu = page.getByRole("menu", { name: switcher });
      await expect(menu).toBeVisible();
      await expect(button).toHaveAttribute("aria-expanded", "true");
      // Focus is on an item; Arrow keys, Home and End move between them, wrapping round.
      const items = menu.getByRole("menuitem");
      const count = await items.count();
      expect(await holdsFocus(menu)).toBe(true);
      await page.keyboard.press("Home");
      await expect(items.first()).toBeFocused();
      await page.keyboard.press("End");
      await expect(items.nth(count - 1)).toBeFocused();
      await page.keyboard.press("ArrowDown");
      await expect(items.first()).toBeFocused();
      await page.keyboard.press("ArrowUp");
      await expect(items.nth(count - 1)).toBeFocused();
      // Escape closes it and gives focus back to the button.
      await page.keyboard.press("Escape");
      await expect(menu).toHaveCount(0);
      await expect(button).toBeFocused();
      await expect(button).toHaveAttribute("aria-expanded", "false");
    }

    // Arrow Down on a switcher opens it too, and Enter on an item follows it.
    const agents = menuButton(page, "Agents");
    await agents.focus();
    await page.keyboard.press("ArrowDown");
    const menu = page.getByRole("menu", { name: "Agents" });
    await expect(menu.getByRole("menuitem", { name: "Keys helper" })).toBeFocused();
    await page.keyboard.press(
      (await menu.getByRole("menuitem").first().textContent())?.includes("Keys helper") === true ? "ArrowDown" : "ArrowUp",
    );
    await expect(menu.getByRole("menuitem", { name: "Keys other" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { level: 1, name: "Keys other" })).toBeVisible();

    // The Agent's ⋯ menu, by keyboard.
    const more = page.getByRole("button", { name: "More Agent actions" });
    await more.focus();
    await page.keyboard.press("Enter");
    const actions = page.getByRole("menu", { name: "Agent actions" });
    await expect(actions).toBeVisible();
    expect(await holdsFocus(actions)).toBe(true);
    await page.keyboard.press("Escape");
    await expect(actions).toHaveCount(0);
    await expect(more).toBeFocused();
  });

  // [11.32]
  test("a keyboard user opens a dialog, stays inside it with Tab, and leaves it with Escape back where they were", async ({
    signedInPage: page,
  }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible();
    const opener = page.getByRole("button", { name: "New Project" });
    await opener.focus();
    await page.keyboard.press("Enter");

    // Announced as a modal dialog with its name, focus on its first control.
    const dialog = page.getByRole("dialog", { name: "New Project" });
    await expect(dialog).toBeVisible();
    await expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(await holdsFocus(dialog)).toBe(true);
    for (let step = 0; step < 8; step++) {
      await page.keyboard.press(step < 4 ? "Tab" : "Shift+Tab");
      expect(await holdsFocus(dialog)).toBe(true);
    }
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(opener).toBeFocused();

    // And it can be filled and submitted from the keyboard alone.
    await page.keyboard.press("Enter");
    await expect(dialog).toBeVisible();
    await page.keyboard.type("Keyboard desk");
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { level: 1, name: "Keyboard desk" })).toBeVisible();
  });

  // [12.83]
  test("the New Project, Edit details and Invite someone dialogs pass the accessibility checks while open, in both Appearances", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    test.setTimeout(120_000);
    await page.goto("/");
    const { organisationId, organisation } = await organisationOf(page);
    const projectId = await createProject(page, organisation, "Dialogs HR");

    const dialogs: { name: string; title: string; path: string; open: () => Promise<void> }[] = [
      {
        name: "New Project",
        title: "New Project",
        path: `/organisations/${organisationId}/projects`,
        open: () => page.getByRole("button", { name: "New Project" }).click(),
      },
      {
        name: "Edit details",
        title: "Project details",
        path: `/organisations/${organisationId}/projects/${projectId}`,
        open: () => page.getByRole("button", { name: "Edit details" }).click(),
      },
      {
        name: "Invite someone",
        title: "Invite someone",
        path: `/organisations/${organisationId}/settings/members`,
        open: () => page.getByRole("button", { name: "Invite someone" }).click(),
      },
    ];

    const violations: Record<string, string[]> = {};
    for (const appearance of APPEARANCES) {
      await page.emulateMedia({ colorScheme: appearance });
      for (const dialog of dialogs) {
        await page.goto(dialog.path);
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 15_000 });
        await page.waitForLoadState("networkidle");
        await dialog.open();
        await expect(page.getByRole("dialog")).toBeVisible();
        await expect(page.getByRole("dialog")).toHaveAccessibleName(dialog.title);
        const found = (await makeAxeBuilder().analyze()).violations.map((violation) => violation.id);
        if (found.length > 0) violations[`${appearance} ${dialog.name}`] = found;
      }
    }
    expect(violations).toEqual({});
  });

  // [11.30]
  test("an Editor reads exact values from the Over time chart by hovering it, and from its table view for any metric", async ({
    signedInPage: page,
  }) => {
    test.setTimeout(120_000);
    const { organisationId, projectId, agentApi } = await organisationWithSpend(page, "Chart");
    expect((await page.request.post(`${agentApi}/versions`, { data: { note: "First release" } })).status()).toBe(201);

    await page.goto(`/organisations/${organisationId}/projects/${projectId}/analytics`);
    const section = page.getByRole("region", { name: "Over time" });
    const chart = section.locator(".recharts-surface").first();
    await expect(chart).toBeVisible({ timeout: 15_000 });

    // Hovering the plot shows a readout of the period under the pointer, its value and sample size.
    const readout = section.getByRole("status", { name: "Chart readout" });
    await expect(readout).toHaveCount(0);
    await chart.scrollIntoViewIfNeeded();
    const box = await chart.boundingBox();
    const today = { x: (box?.width ?? 0) - 30, y: (box?.height ?? 0) / 2 };
    await chart.hover({ position: today });
    await expect(readout).toBeVisible();
    await expect(readout).toContainText(TODAY);
    await expect(readout).toContainText(/Conversations \d+/);
    await expect(readout).toContainText(/n = \d+ Conversations/);

    // The Cost metric reads in dollars, in the readout and in its table view.
    await section.getByLabel("Metric").selectOption("cost_usd");
    await expect(section.getByText(/^Cost per day, from/)).toBeVisible({ timeout: 15_000 });
    await page.mouse.move(0, 0);
    await chart.hover({ position: today });
    await expect(readout).toContainText(/Cost \$\d/);
    await section.getByRole("radio", { name: "Table" }).click();
    const table = section.getByRole("table", { name: "Cost, the numbers behind the chart" });
    await expect(table.getByRole("row")).toHaveCount(31, { timeout: 15_000 });
    await expect(table.getByRole("row").last().getByRole("rowheader")).toContainText(TODAY);
    await expect(table.getByRole("row").last().getByRole("cell").first()).toHaveText(/^\$\d/);
  });
});
