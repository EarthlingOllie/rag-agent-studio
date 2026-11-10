import type { Page } from "@playwright/test";

import { expect, test } from "../fixtures";
import type { MemberCredentials } from "../fixtures/auth";
import { totpCode, totpStep } from "../fixtures/totp";
import { openSection, sidebar } from "../fixtures/navigation";

async function openSecurity(page: Page) {
  await page.goto("/");
  await openSection(page, "Account", "Security");
  await expect(page.getByRole("heading", { name: "Security", level: 1 })).toBeVisible();
}

async function signOutAndEnterPassword(page: Page, member: MemberCredentials) {
  await openSection(page, "Account", "Sign out");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await page.getByLabel("Email").fill(member.email);
  await page.getByLabel("Password").fill(member.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Two-factor authentication" })).toBeVisible();
}

test("a Member enrols in MFA, signs in with a code and a recovery code, then turns MFA off", async ({
  signedInPage: page,
  member,
  makeAxeBuilder,
}) => {
  await openSecurity(page);
  await page.getByRole("button", { name: "Set up two-factor authentication" }).click();
  await expect(page.getByRole("img", { name: "QR code for your authenticator app" })).toBeVisible();
  expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
  const secret = (await page.locator("code").textContent()) ?? "";
  expect(secret).toMatch(/^[A-Z2-7]{32}$/);

  const enrolStep = totpStep();
  await page.getByLabel("Code from your app").fill(totpCode(secret, enrolStep));
  await page.getByRole("button", { name: "Turn on" }).click();

  const list = page.getByRole("list", { name: "Recovery codes" });
  await expect(list.getByRole("listitem")).toHaveCount(10);
  const recoveryCodes = await list.getByRole("listitem").allTextContents();
  expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
  await page.getByRole("button", { name: "I've saved my recovery codes" }).click();
  await expect(page.getByText("10 recovery codes left.", { exact: false })).toBeVisible();
  expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

  // The password alone no longer signs in: a code from the app finishes it.
  await signOutAndEnterPassword(page, member);
  expect(await page.context().cookies()).not.toContainEqual(expect.objectContaining({ name: "studio_session" }));
  expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
  // A code is accepted once, so use the step after the enrolment code (inside the ±1 window).
  await page.getByLabel("Authentication code").fill(totpCode(secret, enrolStep + 1));
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
  await expect(sidebar(page).getByText(member.organisationName)).toBeVisible();

  // A recovery code works once instead of the app.
  await signOutAndEnterPassword(page, member);
  await page.getByRole("button", { name: "Use a recovery code instead" }).click();
  await page.getByLabel("Recovery code").fill(recoveryCodes[0] ?? "");
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
  await openSecurity(page);
  await expect(page.getByText("9 recovery codes left.", { exact: false })).toBeVisible();

  // Turning MFA off needs the password and a code.
  const turnOff = page.getByRole("form", { name: "Turn off two-factor authentication" });
  await turnOff.getByLabel("Password").fill("not the password at all");
  await turnOff.getByLabel("Code from your app or a recovery code").fill(recoveryCodes[1] ?? "");
  await turnOff.getByRole("button", { name: "Turn off" }).click();
  await expect(turnOff.getByRole("alert")).toHaveText("Your password or code is incorrect.");
  await turnOff.getByLabel("Password").fill(member.password);
  await turnOff.getByRole("button", { name: "Turn off" }).click();
  await expect(page.getByRole("button", { name: "Set up two-factor authentication" })).toBeVisible();

  await openSection(page, "Account", "Sign out");
  await page.getByLabel("Email").fill(member.email);
  await page.getByLabel("Password").fill(member.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
});

test("a wrong code keeps the Member on the challenge", async ({ signedInPage: page, member }) => {
  await openSecurity(page);
  await page.getByRole("button", { name: "Set up two-factor authentication" }).click();
  const secret = (await page.locator("code").textContent()) ?? "";
  const enrolStep = totpStep();
  await page.getByLabel("Code from your app").fill(totpCode(secret, enrolStep));
  await page.getByRole("button", { name: "Turn on" }).click();
  await page.getByRole("button", { name: "I've saved my recovery codes" }).click();

  await signOutAndEnterPassword(page, member);
  await page.getByLabel("Authentication code").fill(totpCode(secret, enrolStep + 10));
  await page.getByRole("button", { name: "Verify" }).click();

  await expect(page.getByRole("alert")).toHaveText("That code is incorrect. Try again.");
  await page.getByLabel("Authentication code").fill(totpCode(secret, enrolStep + 1));
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
});
