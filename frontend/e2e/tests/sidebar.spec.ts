import { expect, test } from "../fixtures";
import { breadcrumb, currentSection, navigationButton, openDrawer, openSection, sectionNames, sidebar } from "../fixtures/navigation";

test.describe("Sidebar", () => {
  test("an Owner moves around the Organisation and a Project from the sidebar, which marks where they are", async ({
    signedInPage: page,
    member,
    makeAxeBuilder,
  }) => {
    await page.goto("/");
    const me = (await (await page.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
    const organisation = `/api/organisations/${me.organisations[0]?.id ?? ""}`;
    const project = await page.request.post(`${organisation}/projects`, { data: { name: "Northwind HR" } });
    expect(project.status()).toBe(201);
    const { id: projectId } = (await project.json()) as { id: string };
    const agent = await page.request.post(`${organisation}/projects/${projectId}/agents`, { data: { name: "HR helper" } });
    expect(agent.status()).toBe(201);

    // The Organisation: its name (one Organisation, so no switcher), then its links.
    await expect(sidebar(page).getByText(member.organisationName)).toBeVisible();
    expect(await sectionNames(page, "Organisation sections")).toEqual(["Projects", "Cost", "Settings"]);
    expect(await currentSection(page, "Organisation sections")).toBe("Projects");
    await openSection(page, "Organisation sections", "Cost");
    await expect(page.getByRole("heading", { level: 1, name: "Organisation cost" })).toBeVisible();
    expect(await currentSection(page, "Organisation sections")).toBe("Cost");
    await openSection(page, "Organisation sections", "Settings");
    await expect(page.getByRole("heading", { level: 1, name: "Organisation settings" })).toBeVisible();
    expect(await currentSection(page, "Organisation sections")).toBe("Settings");

    // Into the Project, from the Projects list.
    await openSection(page, "Organisation sections", "Projects");
    await page.getByRole("table", { name: "Projects" }).getByRole("link", { name: "Northwind HR" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Northwind HR" })).toBeVisible();
    expect(await sectionNames(page, "Project sections")).toEqual(["Documents", "Instructions", "Agents", "Conversations", "Analytics", "Settings"]);
    expect(await currentSection(page, "Project sections")).toBe("Documents");
    expect(await currentSection(page, "Organisation sections")).toBe("");

    // An Agent keeps Agents current.
    await openSection(page, "Project sections", "Agents");
    await page.getByRole("table", { name: "Agents" }).getByRole("link", { name: "HR helper" }).click();
    // The Agent's name is the page's h1.
    await expect(page.getByRole("heading", { level: 1, name: "HR helper" })).toBeVisible();
    expect(await currentSection(page, "Project sections")).toBe("Agents");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // The Project switcher goes back to All Projects.
    await openSection(page, "Projects", "All Projects");
    await expect(page.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible();
    await expect(sidebar(page).getByRole("list", { name: "Project sections" })).toHaveCount(0);
  });

  test("the main content keeps its 1160 px column beside a sidebar of about 240 px", async ({ signedInPage: page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible();

    const side = await sidebar(page).boundingBox();
    const main = await page.getByRole("main").boundingBox();
    expect(side?.width).toBeGreaterThanOrEqual(232);
    expect(side?.width).toBeLessThanOrEqual(248);
    expect(main?.width).toBeLessThanOrEqual(1160);
    // Centred in the space beside the sidebar.
    const left = (main?.x ?? 0) - 240;
    const right = 1440 - ((main?.x ?? 0) + (main?.width ?? 0));
    expect(Math.abs(left - right)).toBeLessThanOrEqual(2);
  });

  test("on a phone the sidebar is a drawer behind Open navigation, which holds focus and closes on Escape, outside or a link", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible();

    // The content gets the full width; the sidebar waits behind the button.
    await expect(sidebar(page)).toBeHidden();
    const main = await page.getByRole("main").boundingBox();
    expect(main?.x ?? 0).toBeLessThan(40);
    const button = navigationButton(page);
    await expect(button).toBeVisible();

    // Opening focuses the current link; Tab and Shift+Tab stay inside.
    await button.focus();
    await page.keyboard.press("Enter");
    const drawer = page.getByRole("dialog", { name: "Navigation" });
    await expect(drawer.getByRole("link", { name: "Projects", exact: true })).toBeFocused();
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    for (let step = 0; step < 6; step++) {
      await page.keyboard.press(step < 3 ? "Tab" : "Shift+Tab");
      expect(await drawer.evaluate((element) => element.contains(document.activeElement))).toBe(true);
    }

    // Escape closes it and focus returns to the button.
    await page.keyboard.press("Escape");
    await expect(drawer).toHaveCount(0);
    await expect(button).toBeFocused();

    // A press outside it closes it too.
    await openDrawer(page);
    await page.mouse.click(380, 600);
    await expect(drawer).toHaveCount(0);
    await expect(button).toBeFocused();

    // Following a link opens its page and closes it.
    await (await openDrawer(page)).getByRole("link", { name: "Settings", exact: true }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Organisation settings" })).toBeVisible();
    await expect(drawer).toHaveCount(0);
    await expect(button).toBeFocused();
    const reopened = await openDrawer(page);
    await expect(reopened.getByRole("link", { name: "Settings", exact: true })).toHaveAttribute("aria-current", "page");
    await expect(reopened.getByRole("link", { name: "Settings", exact: true })).toBeFocused();
  });

  test("the breadcrumb is a plain path of links, and on a phone shows only its last two crumbs on one row", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");
    const me = (await (await page.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
    const organisationId = me.organisations[0]?.id ?? "";
    const organisation = `/api/organisations/${organisationId}`;
    const project = await page.request.post(`${organisation}/projects`, { data: { name: "Northwind HR" } });
    const { id: projectId } = (await project.json()) as { id: string };
    const agent = await page.request.post(`${organisation}/projects/${projectId}/agents`, { data: { name: "HR helper" } });
    const { id: agentId } = (await agent.json()) as { id: string };

    await page.goto(`/organisations/${organisationId}/projects/${projectId}/agents/${agentId}/versions`);
    await expect(page.getByRole("heading", { level: 1, name: "HR helper" })).toBeVisible();
    expect(await breadcrumb(page)).toEqual({ crumbs: ["Northwind HR", "Agents", "HR helper"], current: "HR helper" });
    const crumbs = page.getByRole("banner").getByRole("navigation", { name: "Breadcrumb" });
    await expect(crumbs.getByRole("button")).toHaveCount(0);

    // Profile, Security and Sign out are in the account menu only.
    expect(await sectionNames(page, "Account")).toEqual(["Profile", "Security", "Sign out"]);
    for (const name of ["Profile", "Security"]) await expect(page.getByRole("link", { name, exact: true })).toHaveCount(0);

    // A crumb leads back up a level.
    await crumbs.getByRole("link", { name: "Agents", exact: true }).click();
    await expect(page.getByRole("table", { name: "Agents" })).toBeVisible();
    expect(await breadcrumb(page)).toEqual({ crumbs: ["Northwind HR", "Agents"], current: "Agents" });

    // On a phone: the last two crumbs, the top bar one row high, and no sideways scroll.
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`/organisations/${organisationId}/projects/${projectId}/agents/${agentId}`);
    await expect(page.getByRole("heading", { level: 1, name: "HR helper" })).toBeVisible();
    expect(await breadcrumb(page)).toEqual({ crumbs: ["Agents", "HR helper"], current: "HR helper" });
    await expect(page.getByRole("button", { name: "Show the whole path" })).toHaveCount(0);
    const bar = await page.getByRole("banner").boundingBox();
    expect(bar?.height ?? 0).toBeLessThanOrEqual(64);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
  });
});
