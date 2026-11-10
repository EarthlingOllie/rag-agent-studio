import type { Browser, Page } from "@playwright/test";

import { expect, test } from "../fixtures";
import { type MemberCredentials, newMember } from "../fixtures/auth";
import { openSection } from "../fixtures/navigation";

async function openProjects(page: Page) {
  await page.goto("/");
  await openSection(page, "Organisation sections", "Projects");
  await expect(page.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible();
}

async function createProject(page: Page, name: string, description: string) {
  await openProjects(page);
  await page.getByRole("button", { name: "New Project" }).click();
  const form = page.getByRole("form", { name: "New Project" });
  await form.getByLabel("Name").fill(name);
  await form.getByLabel("Description").fill(description);
  await form.getByRole("button", { name: "Create Project" }).click();
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
}

/** The Owner invites a new person with a copied link; they create an account in their own browser. */
async function inviteNewEditor(owner: Page, browser: Browser, person: MemberCredentials): Promise<Page> {
  await owner.goto("/");
  await openSection(owner, "Organisation sections", "Settings");
  await openSection(owner, "Organisation settings", "Members");
  await expect(owner.getByRole("table", { name: "Members" })).toBeVisible();
  const form = owner.getByRole("form", { name: "Invite someone" });
  await form.getByLabel("Email", { exact: true }).fill(person.email);
  await form.getByLabel("Role").selectOption("Editor");
  await form.getByLabel("Email the invite link").uncheck();
  await form.getByRole("button", { name: "Invite" }).click();
  const link = new URL(await owner.getByLabel(`Invite link for ${person.email}`).inputValue());
  const page = await (await browser.newContext()).newPage();
  await page.goto(link.pathname + link.search);
  await page.getByLabel("Your name").fill(person.name);
  await page.getByLabel("Password").fill(person.password);
  await page.getByRole("button", { name: "Create account and join" }).click();
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
  return page;
}

test.describe("Projects", () => {
  test("an Owner creates, renames, archives and restores a Project, and each step is audited", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    await createProject(page, "HR handbook", "Policies for the HR Agent");

    // The Project page has a section per area, each a placeholder for now.
    for (const tab of ["Documents", "Instructions", "Agents", "Conversations", "Analytics"]) {
      await openSection(page, "Project sections", tab);
      await expect(page.getByRole("heading", { level: 2, name: tab })).toBeVisible();
    }
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // Rename and describe it.
    await page.getByRole("button", { name: "Edit details" }).click();
    const details = page.getByRole("form", { name: "Project details" });
    await details.getByLabel("Name").fill("People team");
    await details.getByLabel("Description").fill("Policies and benefits");
    await details.getByRole("button", { name: "Save" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "People team" })).toBeVisible();

    // It is listed with its counts.
    await openSection(page, "Projects", "All Projects");
    const projects = page.getByRole("table", { name: "Projects" });
    await expect(projects.getByRole("row").filter({ hasText: "People team" }).getByRole("cell")).toHaveText([
      "People team",
      "Policies and benefits",
      "0",
      "0",
    ]);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // Archive it: it leaves the main list and refuses changes.
    await projects.getByRole("link", { name: "People team" }).click();
    await page.getByRole("button", { name: "More Project actions" }).click();
    await page.getByRole("menu", { name: "Project actions" }).getByRole("menuitem", { name: "Archive" }).click();
    await page.getByRole("button", { name: "Yes, archive People team" }).click();
    await expect(page.getByText(/This Project is archived/)).toBeVisible();
    const projectUrl = new URL(page.url()).pathname.replace(/^\//, "/api/");
    const refused = await page.request.patch(projectUrl, { data: { name: "Sneaky rename" } });
    expect(refused.status()).toBe(409);
    await openSection(page, "Projects", "All Projects");
    await expect(page.getByText(/No Projects yet/)).toBeVisible();

    // Restore it from the archived list.
    await page.getByRole("button", { name: "Show archived Projects" }).click();
    await page.getByRole("button", { name: "Restore People team" }).click();
    await expect(page.getByText("People team was restored.")).toBeVisible();
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    await page.getByRole("button", { name: "Show active Projects" }).click();
    await expect(projects.getByRole("link", { name: "People team" })).toBeVisible();

    // Create, archive and restore are in the Audit tab.
    await openSection(page, "Organisation sections", "Settings");
    await openSection(page, "Organisation settings", "Audit");
    const audit = page.getByRole("table", { name: "Audit Events" });
    for (const action of ["project.created", "project.archived", "project.restored"]) {
      await expect(audit.getByRole("cell", { name: action })).toHaveCount(1);
    }
  });

  test("an Editor creates and archives a Project but only an Owner restores it", async ({ signedInPage: page, browser }) => {
    const editorPage = await inviteNewEditor(page, browser, newMember({ name: "Project Editor" }));

    await createProject(editorPage, "Sales enablement", "Decks and pricing");
    await editorPage.getByRole("button", { name: "More Project actions" }).click();
    await editorPage.getByRole("menu", { name: "Project actions" }).getByRole("menuitem", { name: "Archive" }).click();
    await editorPage.getByRole("button", { name: "Yes, archive Sales enablement" }).click();
    await expect(editorPage.getByText("Only Owners can restore it.")).toBeVisible();
    await expect(editorPage.getByRole("button", { name: "Restore Sales enablement" })).toHaveCount(0);
    const restoreUrl = `${new URL(editorPage.url()).pathname.replace(/^\//, "/api/")}/restore`;
    expect((await editorPage.request.post(restoreUrl)).status()).toBe(403);

    await openProjects(page);
    await page.getByRole("button", { name: "Show archived Projects" }).click();
    await page.getByRole("button", { name: "Restore Sales enablement" }).click();
    await expect(page.getByText("Sales enablement was restored.")).toBeVisible();

    await openProjects(editorPage);
    await expect(editorPage.getByRole("table", { name: "Projects" }).getByRole("link", { name: "Sales enablement" })).toBeVisible();
    await editorPage.context().close();
  });
});
