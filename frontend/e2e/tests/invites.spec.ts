import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";

import { AXE_TAGS, expect, test } from "../fixtures";
import { newMember, signUp } from "../fixtures/auth";
import { latestEmailTo, linkPath } from "../fixtures/mailpit";

async function openMembers(page: Page) {
  await page.goto("/");
  await page.getByRole("navigation", { name: "Organisation" }).getByRole("link", { name: "Organisation settings" }).click();
  await page.getByRole("navigation", { name: "Organisation settings" }).getByRole("link", { name: "Members" }).click();
  await expect(page.getByRole("form", { name: "Invite someone" })).toBeVisible();
  // Wait for the Members list, so its loading status has gone before the invite's status appears.
  await expect(page.getByRole("table", { name: "Members" })).toBeVisible();
}

test.describe("invites", () => {
  test("an Owner invites an Editor, who opens the email in Mailpit and joins with a new account", async ({
    signedInPage: page,
    member,
    browser,
    makeAxeBuilder,
  }) => {
    const invited = newMember({ name: "Invited Editor" });
    await openMembers(page);
    const form = page.getByRole("form", { name: "Invite someone" });
    await form.getByLabel("Email", { exact: true }).fill(invited.email);
    await form.getByLabel("Role").selectOption("Editor");
    await form.getByRole("button", { name: "Invite" }).click();
    await expect(page.getByRole("status")).toContainText(`We emailed an invite to ${invited.email}.`);
    const pending = page.getByRole("table", { name: "Pending invites" });
    await expect(pending.getByRole("cell", { name: invited.email, exact: true })).toBeVisible();
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    const email = await latestEmailTo(page.request, invited.email);
    expect(email.Subject).toBe(`Join ${member.organisationName} on RAG Agent Studio`);
    expect(email.Text).toContain(`${member.name} has invited you to join ${member.organisationName}`);
    const inviteLink = linkPath(email.Text, "/accept-invite");

    const invitedContext = await browser.newContext();
    const invitedPage = await invitedContext.newPage();
    await invitedPage.goto(inviteLink);
    await expect(invitedPage.getByRole("heading", { name: `Join ${member.organisationName}` })).toBeVisible();
    await expect(invitedPage.getByText(`invited ${invited.email} to join`)).toBeVisible();
    expect((await new AxeBuilder({ page: invitedPage }).withTags(AXE_TAGS).analyze()).violations).toEqual([]);
    await invitedPage.getByLabel("Your name").fill(invited.name);
    await invitedPage.getByLabel("Password").fill(invited.password);
    await invitedPage.getByRole("button", { name: "Create account and join" }).click();

    await expect(invitedPage.getByRole("heading", { name: "Projects" })).toBeVisible();
    await expect(invitedPage.getByText(member.organisationName)).toBeVisible();
    // An Editor: no Owner-only tabs.
    await invitedPage.getByRole("link", { name: "Organisation settings" }).click();
    const tabs = invitedPage.getByRole("navigation", { name: "Organisation settings" });
    await expect(tabs.getByRole("link", { name: "General" })).toBeVisible();
    await expect(tabs.getByRole("link", { name: "Members" })).toHaveCount(0);

    // The new Member signs in again with the password they chose.
    await invitedContext.clearCookies();
    await invitedPage.goto("/sign-in");
    await invitedPage.getByLabel("Email").fill(invited.email);
    await invitedPage.getByLabel("Password").fill(invited.password);
    await invitedPage.getByRole("button", { name: "Sign in" }).click();
    await expect(invitedPage.getByText(member.organisationName)).toBeVisible();

    // The link worked once.
    await invitedContext.clearCookies();
    await invitedPage.goto(inviteLink);
    await expect(invitedPage.getByRole("alert")).toContainText("This invite link is invalid or has expired.");

    // The Owner sees the invite gone from Pending and the events in the Audit tab.
    await page.reload();
    await expect(page.getByText("No pending invites.")).toBeVisible();
    await page.getByRole("navigation", { name: "Organisation settings" }).getByRole("link", { name: "Audit" }).click();
    await expect(page.getByRole("cell", { name: "invite.created" })).toBeVisible();
    await expect(page.getByRole("cell", { name: "invite.accepted" })).toBeVisible();
    await invitedContext.close();
  });

  test("an existing Member accepts a copied link, and a revoked link stops working", async ({
    signedInPage: page,
    member,
    browser,
  }) => {
    const colleague = newMember();
    const colleagueContext = await browser.newContext();
    const colleaguePage = await colleagueContext.newPage();
    await signUp(colleaguePage.request, colleague);

    await openMembers(page);
    const form = page.getByRole("form", { name: "Invite someone" });
    await form.getByLabel("Email", { exact: true }).fill(colleague.email);
    await form.getByLabel("Role").selectOption("Owner");
    await form.getByLabel("Email the invite link").uncheck();
    await form.getByRole("button", { name: "Invite" }).click();
    await expect(page.getByRole("status")).toContainText(`Copy the link and send it to ${colleague.email}.`);
    const link = await page.getByLabel(`Invite link for ${colleague.email}`).inputValue();

    await colleaguePage.goto(new URL(link).pathname + new URL(link).search);
    await colleaguePage.getByRole("button", { name: `Join ${member.organisationName}` }).click();
    await expect(colleaguePage.getByRole("heading", { name: "Projects" })).toBeVisible();
    await expect(colleaguePage.getByText(member.organisationName)).toBeVisible();
    const me = (await (await colleaguePage.request.get("/api/auth/me")).json()) as { organisations: { name: string; role: string }[] };
    expect(me.organisations.map((o) => [o.name, o.role]).sort()).toEqual(
      [
        [colleague.organisationName, "owner"],
        [member.organisationName, "owner"],
      ].sort(),
    );

    // A second invite, revoked before it is used.
    const late = newMember();
    await form.getByLabel("Email", { exact: true }).fill(late.email);
    await form.getByRole("button", { name: "Invite" }).click();
    const lateLink = await page.getByLabel(`Invite link for ${late.email}`).inputValue();
    await page.getByRole("button", { name: `Revoke invite for ${late.email}` }).click();
    await expect(page.getByRole("button", { name: `Revoke invite for ${late.email}` })).toHaveCount(0);
    const latePage = await (await browser.newContext()).newPage();
    await latePage.goto(new URL(lateLink).pathname + new URL(lateLink).search);
    await expect(latePage.getByRole("alert")).toContainText("This invite link is invalid or has expired.");
    await colleagueContext.close();
  });
});
