import { expect, test } from "../fixtures";
import { openSection } from "../fixtures/navigation";

test.describe("Project Instructions", () => {
  test("an Owner formats Instructions in the markdown editor and the markdown is saved and audited", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    await page.goto("/");
    await openSection(page, "Organisation sections", "Projects");
    await page.getByRole("button", { name: "New Project" }).click();
    const newProject = page.getByRole("form", { name: "New Project" });
    await newProject.getByLabel("Name").fill("Northwind HR");
    await newProject.getByRole("button", { name: "Create Project" }).click();
    await openSection(page, "Project sections", "Instructions");

    // Write formatted text the way an Editor would: toolbar buttons and typing.
    const editor = page.getByRole("textbox", { name: "Project Instructions" });
    const toolbar = page.getByRole("toolbar", { name: "Project Instructions formatting" });
    await editor.click();
    await toolbar.getByRole("button", { name: "Heading" }).click();
    await page.keyboard.type("House rules");
    await page.keyboard.press("Enter");
    await toolbar.getByRole("button", { name: "Bulleted list" }).click();
    await page.keyboard.type("Answer in ");
    await toolbar.getByRole("button", { name: "Bold" }).click();
    await page.keyboard.type("British English");
    await toolbar.getByRole("button", { name: "Bold" }).click();
    await page.keyboard.type(". Use <context> & snake_case.");
    await expect(editor.getByRole("heading", { level: 2, name: "House rules" })).toBeVisible();
    await expect(editor.locator("strong")).toHaveText("British English");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    await page.getByRole("button", { name: "Save Instructions" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Instructions saved" })).toBeVisible({ timeout: 15_000 });

    // The API holds exactly the markdown, and the Markdown view shows it after a reload.
    const markdown = "## House rules\n\n- Answer in **British English**. Use <context> & snake_case.";
    const instructionsUrl = page.url().replace(/^https?:\/\/[^/]+/, "/api");
    const saved = await page.request.get(instructionsUrl);
    expect(((await saved.json()) as { markdown: string }).markdown).toEqual(markdown);
    await page.reload();
    await page.getByRole("button", { name: "Markdown" }).click({ timeout: 15_000 });
    await expect(page.getByRole("textbox", { name: "Project Instructions (Markdown)" })).toHaveValue(markdown);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // The edit is in the Audit log.
    const me = (await (await page.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
    const audit = await page.request.get(`/api/organisations/${me.organisations[0]?.id ?? ""}/audit-events`, {
      params: { action: "project.instructions_updated" },
    });
    const { items } = (await audit.json()) as { items: { after: { instructions: string } }[] };
    expect(items.map((item) => item.after.instructions)).toEqual([markdown]);

    // Archiving the Project with the tab open locks the editor in place; restoring unlocks it.
    await page.getByRole("button", { name: "Markdown" }).click();
    await expect(editor).toHaveAttribute("contenteditable", "true");
    await page.getByRole("button", { name: "More Project actions" }).click();
    await page.getByRole("menu", { name: "Project actions" }).getByRole("menuitem", { name: "Archive" }).click();
    await page.getByRole("button", { name: "Yes, archive Northwind HR" }).click();
    await expect(editor).toHaveAttribute("contenteditable", "false");
    await expect(page.getByRole("button", { name: "Save Instructions" })).toHaveCount(0);
    await page.getByRole("button", { name: "Restore Northwind HR" }).click();
    await expect(editor).toHaveAttribute("contenteditable", "true");
    await editor.click();
    await page.keyboard.press("End");
    await page.keyboard.type(" Thanks.");
    await expect(editor).toContainText("snake_case. Thanks.");
  });
});
