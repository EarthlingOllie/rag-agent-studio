import type { Browser, Page } from "@playwright/test";

import { expect, test } from "../fixtures";
import { type MemberCredentials, newMember } from "../fixtures/auth";

const LAST_OWNER = "An Organisation needs at least one Owner. Make someone else an Owner first.";

async function openSettings(page: Page, tab?: "Members") {
  await page.goto("/");
  await page.getByRole("navigation", { name: "Organisation" }).getByRole("link", { name: "Organisation settings" }).click();
  if (tab) {
    await page.getByRole("navigation", { name: "Organisation settings" }).getByRole("link", { name: tab }).click();
    await expect(page.getByRole("table", { name: "Members" })).toBeVisible();
  }
}

async function organisationId(page: Page): Promise<string> {
  const me = (await (await page.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
  return me.organisations[0]?.id ?? "";
}

/** The Owner invites a new person with a copied link; they create an account in their own browser. */
async function inviteNewEditor(owner: Page, browser: Browser, person: MemberCredentials): Promise<Page> {
  await openSettings(owner, "Members");
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

test.describe("members and roles", () => {
  test("an Owner sees roles, can't demote the last Owner, changes roles and removes a Member, whose access ends", async ({
    signedInPage: page,
    member,
    browser,
    makeAxeBuilder,
  }) => {
    const editor = newMember({ name: "Grace Editor" });
    const editorPage = await inviteNewEditor(page, browser, editor);
    const id = await organisationId(page);

    // The Editor doesn't see Owner-only tabs, and the API refuses them too.
    await openSettings(editorPage);
    const editorTabs = editorPage.getByRole("navigation", { name: "Organisation settings" });
    await expect(editorTabs.getByRole("link", { name: "General" })).toBeVisible();
    await expect(editorTabs.getByRole("link", { name: "Members" })).toHaveCount(0);
    await expect(editorTabs.getByRole("link", { name: "Audit" })).toHaveCount(0);
    expect((await editorPage.request.get(`/api/organisations/${id}/members`)).status()).toBe(403);
    expect((await editorPage.request.get(`/api/organisations/${id}/audit-events`)).status()).toBe(403);

    // The Owner sees every Member with their role.
    await page.reload();
    const members = page.getByRole("table", { name: "Members" });
    await expect(members.getByRole("cell", { name: `${member.name} (you)` })).toBeVisible();
    await expect(page.getByLabel(`Role for ${member.name}`)).toHaveValue("owner");
    await expect(page.getByLabel(`Role for ${editor.name}`)).toHaveValue("editor");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // The last Owner can't step down.
    await page.getByLabel(`Role for ${member.name}`).selectOption("Editor");
    await expect(page.getByRole("alert")).toContainText(LAST_OWNER);
    await expect(page.getByLabel(`Role for ${member.name}`)).toHaveValue("owner");

    // Promote the Editor: the Owner-only tabs appear for them.
    await page.getByLabel(`Role for ${editor.name}`).selectOption("Owner");
    await expect(page.getByText(`${editor.name} is now an Owner.`)).toBeVisible();
    await editorPage.reload();
    await expect(editorTabs.getByRole("link", { name: "Members" })).toBeVisible();
    await page.getByLabel(`Role for ${editor.name}`).selectOption("Editor");
    await expect(page.getByText(`${editor.name} is now an Editor.`)).toBeVisible();

    // Remove them: their very next request is refused.
    await page.getByRole("button", { name: `Remove ${editor.name}` }).click();
    await page.getByRole("button", { name: `Yes, remove ${editor.name}` }).click();
    await expect(page.getByText(`${editor.name} was removed and can no longer open this Organisation.`)).toBeVisible();
    await expect(members.getByRole("row")).toHaveCount(2);
    expect((await editorPage.request.get(`/api/organisations/${id}`)).status()).toBe(404);
    await editorPage.reload();
    await expect(editorPage.getByRole("heading", { name: "Organisation not found" })).toBeVisible();

    // Each change is in the Audit tab.
    await page.getByRole("navigation", { name: "Organisation settings" }).getByRole("link", { name: "Audit" }).click();
    const audit = page.getByRole("table", { name: "Audit Events" });
    await expect(audit.getByRole("cell", { name: "member.role_changed" })).toHaveCount(2);
    await expect(audit.getByRole("cell", { name: "member.removed" })).toHaveCount(1);
    await editorPage.context().close();
  });

  test("an Editor leaves, and the last Owner can't", async ({ signedInPage: page, member, browser }) => {
    const editor = newMember({ name: "Leaving Editor" });
    const editorPage = await inviteNewEditor(page, browser, editor);

    await openSettings(editorPage);
    await editorPage.getByRole("button", { name: `Leave ${member.organisationName}` }).click();
    await editorPage.getByRole("button", { name: `Yes, leave ${member.organisationName}` }).click();
    await expect(editorPage.getByText("You don't belong to any Organisation yet.")).toBeVisible();

    await openSettings(page);
    await page.getByRole("button", { name: `Leave ${member.organisationName}` }).click();
    await page.getByRole("button", { name: `Yes, leave ${member.organisationName}` }).click();
    await expect(page.getByRole("alert")).toContainText(LAST_OWNER);

    await page.getByRole("navigation", { name: "Organisation settings" }).getByRole("link", { name: "Audit" }).click();
    await expect(page.getByRole("table", { name: "Audit Events" }).getByRole("cell", { name: "member.left" })).toHaveCount(1);
    await editorPage.context().close();
  });
});
