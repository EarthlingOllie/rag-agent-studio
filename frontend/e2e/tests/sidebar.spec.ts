import { expect, test } from "../fixtures";
import { currentSection, openSection, sectionNames, sidebar } from "../fixtures/navigation";

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
});
