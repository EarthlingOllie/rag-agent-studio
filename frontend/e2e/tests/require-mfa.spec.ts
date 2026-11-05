import AxeBuilder from "@axe-core/playwright";
import type { Browser, Page } from "@playwright/test";

import { AXE_TAGS, expect, test } from "../fixtures";
import { type MemberCredentials, newMember } from "../fixtures/auth";
import { totpCode, totpStep } from "../fixtures/totp";

const MFA_REQUIRED = "This Organisation requires MFA. Turn on MFA for your account to continue.";

function organisationNav(page: Page) {
  return page.getByRole("navigation", { name: "Organisation" });
}

/** Turns MFA on from the Security page; returns the secret and the step the confirming code used. */
async function enrol(page: Page): Promise<{ secret: string; step: number }> {
  await page.getByRole("button", { name: "Set up two-factor authentication" }).click();
  const secret = (await page.locator("code").textContent()) ?? "";
  const step = totpStep();
  await page.getByLabel("Code from your app").fill(totpCode(secret, step));
  await page.getByRole("button", { name: "Turn on" }).click();
  await expect(page.getByRole("list", { name: "Recovery codes" }).getByRole("listitem")).toHaveCount(10);
  await page.getByRole("button", { name: "I've saved my recovery codes" }).click();
  await expect(page.getByText("10 recovery codes left.", { exact: false })).toBeVisible();
  return { secret, step };
}

/** The Owner invites a new person with a copied link; they create an account in their own browser. */
async function inviteNewEditor(owner: Page, browser: Browser, person: MemberCredentials): Promise<Page> {
  await owner.goto("/");
  await organisationNav(owner).getByRole("link", { name: "Organisation settings" }).click();
  await owner.getByRole("navigation", { name: "Organisation settings" }).getByRole("link", { name: "Members" }).click();
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

test("an Owner requires MFA, and an Editor is forced to enrol on their next visit", async ({
  signedInPage: owner,
  member,
  browser,
  makeAxeBuilder,
}) => {
  const editor = newMember({ name: "Grace Editor" });
  const editorPage = await inviteNewEditor(owner, browser, editor);
  const organisationId = ((await (await owner.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] })
    .organisations[0]?.id;

  // The Owner turns MFA on for themselves, then requires it in Organisation settings.
  await organisationNav(owner).getByRole("link", { name: "Security" }).click();
  await enrol(owner);
  await organisationNav(owner).getByRole("link", { name: "Organisation settings" }).click();
  const policy = owner.getByRole("region", { name: "Two-factor authentication" });
  await expect(policy).toContainText("Members choose whether to use two-factor authentication.");
  await policy.getByRole("button", { name: "Require two-factor authentication" }).click();
  await expect(policy).toContainText("Every Member must use two-factor authentication.");
  await expect(policy.getByRole("button", { name: "Stop requiring two-factor authentication" })).toBeVisible();
  expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

  // The Editor's next visit: signing in again lands on enrolment, and nothing else is offered.
  await editorPage.getByRole("button", { name: "Sign out" }).click();
  await editorPage.getByLabel("Email").fill(editor.email);
  await editorPage.getByLabel("Password").fill(editor.password);
  await editorPage.getByRole("button", { name: "Sign in" }).click();
  await expect(editorPage.getByRole("heading", { name: "Security", level: 1 })).toBeVisible();
  await expect(
    editorPage.getByText(`${member.organisationName} requires two-factor authentication. Set it up to continue.`),
  ).toBeVisible();
  await expect(organisationNav(editorPage).getByRole("link", { name: "Projects" })).toHaveCount(0);
  expect((await new AxeBuilder({ page: editorPage }).withTags(AXE_TAGS).analyze()).violations).toEqual([]);
  // Typing another page's address leads back to enrolment, and the API refuses the Organisation.
  await editorPage.goto(`/organisations/${organisationId ?? ""}/settings`);
  await expect(editorPage.getByRole("heading", { name: "Security", level: 1 })).toBeVisible();
  const refused = await editorPage.request.get(`/api/organisations/${organisationId ?? ""}`);
  expect(refused.status()).toBe(403);
  expect(await refused.json()).toEqual({ detail: MFA_REQUIRED });

  // Once enrolled, the Organisation opens as usual.
  const { secret, step } = await enrol(editorPage);
  await organisationNav(editorPage).getByRole("link", { name: "Projects" }).click();
  await expect(editorPage.getByRole("heading", { name: "Projects" })).toBeVisible();
  expect((await editorPage.request.get(`/api/organisations/${organisationId ?? ""}`)).status()).toBe(200);

  // While the Organisation requires MFA, the Editor can't turn it off.
  await organisationNav(editorPage).getByRole("link", { name: "Security" }).click();
  const turnOff = editorPage.getByRole("form", { name: "Turn off two-factor authentication" });
  await turnOff.getByLabel("Password").fill(editor.password);
  await turnOff.getByLabel("Code from your app or a recovery code").fill(totpCode(secret, step + 1));
  await turnOff.getByRole("button", { name: "Turn off" }).click();
  await expect(turnOff.getByRole("alert")).toHaveText(
    `MFA can't be turned off while ${member.organisationName} requires it.`,
  );

  // The policy change is in the Owner's Audit tab.
  await owner.getByRole("navigation", { name: "Organisation settings" }).getByRole("link", { name: "Audit" }).click();
  await expect(
    owner.getByRole("table", { name: "Audit Events" }).getByRole("cell", { name: "organisation.mfa_policy_changed" }),
  ).toHaveCount(1);
  await editorPage.context().close();
});
