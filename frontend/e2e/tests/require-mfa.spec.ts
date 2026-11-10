import AxeBuilder from "@axe-core/playwright";
import type { Browser, Page } from "@playwright/test";

import { AXE_TAGS, expect, test } from "../fixtures";
import { type MemberCredentials, newMember } from "../fixtures/auth";
import { totpCode, totpStep } from "../fixtures/totp";
import { openSection, sectionNames } from "../fixtures/navigation";

const MFA_REQUIRED = "This Organisation requires MFA. Turn on MFA for your account to continue.";

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
  await openSection(owner, "Organisation sections", "Settings");
  await openSection(owner, "Organisation settings", "Members");
  await expect(owner.getByRole("table", { name: "Members" })).toBeVisible();
  await owner.getByRole("button", { name: "Invite someone" }).click();
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
  await openSection(owner, "Organisation sections", "Security");
  await enrol(owner);
  await openSection(owner, "Organisation sections", "Settings");
  const policy = owner.getByRole("region", { name: "Two-factor authentication" });
  await expect(policy).toContainText("Members choose whether to use two-factor authentication.");
  await policy.getByRole("button", { name: "Require two-factor authentication" }).click();
  await expect(policy).toContainText("Every Member must use two-factor authentication.");
  await expect(policy.getByRole("button", { name: "Stop requiring two-factor authentication" })).toBeVisible();
  expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

  // The Editor's next visit: signing in again lands on enrolment, and nothing else is offered.
  await openSection(editorPage, "Account", "Sign out");
  await editorPage.getByLabel("Email").fill(editor.email);
  await editorPage.getByLabel("Password").fill(editor.password);
  await editorPage.getByRole("button", { name: "Sign in" }).click();
  await expect(editorPage.getByRole("heading", { name: "Security", level: 1 })).toBeVisible();
  await expect(
    editorPage.getByText(`${member.organisationName} requires two-factor authentication. Set it up to continue.`),
  ).toBeVisible();
  expect(await sectionNames(editorPage, "Organisation sections")).toEqual(["Security"]);
  expect((await new AxeBuilder({ page: editorPage }).withTags(AXE_TAGS).analyze()).violations).toEqual([]);
  // Typing another page's address leads back to enrolment, and the API refuses the Organisation.
  await editorPage.goto(`/organisations/${organisationId ?? ""}/settings`);
  await expect(editorPage.getByRole("heading", { name: "Security", level: 1 })).toBeVisible();
  const refused = await editorPage.request.get(`/api/organisations/${organisationId ?? ""}`);
  expect(refused.status()).toBe(403);
  expect(await refused.json()).toEqual({ detail: MFA_REQUIRED });

  // Once enrolled, the Organisation opens as usual.
  const { secret, step } = await enrol(editorPage);
  await openSection(editorPage, "Organisation sections", "Projects");
  await expect(editorPage.getByRole("heading", { name: "Projects" })).toBeVisible();
  expect((await editorPage.request.get(`/api/organisations/${organisationId ?? ""}`)).status()).toBe(200);

  // While the Organisation requires MFA, the Editor can't turn it off.
  await openSection(editorPage, "Organisation sections", "Security");
  const turnOff = editorPage.getByRole("form", { name: "Turn off two-factor authentication" });
  await turnOff.getByLabel("Password").fill(editor.password);
  await turnOff.getByLabel("Code from your app or a recovery code").fill(totpCode(secret, step + 1));
  await turnOff.getByRole("button", { name: "Turn off" }).click();
  await expect(turnOff.getByRole("alert")).toHaveText(
    `MFA can't be turned off while ${member.organisationName} requires it.`,
  );

  // The policy change is in the Owner's Audit tab.
  await openSection(owner, "Organisation settings", "Audit");
  await expect(
    owner.getByRole("table", { name: "Audit Events" }).getByRole("cell", { name: "organisation.mfa_policy_changed" }),
  ).toHaveCount(1);
  await editorPage.context().close();
});
