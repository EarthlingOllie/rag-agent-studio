import { expect, test } from "../fixtures";
import { newMember, signUp } from "../fixtures/auth";
import { latestEmailTo, linkPath } from "../fixtures/mailpit";
import { openSection } from "../fixtures/navigation";

const NEW_PASSWORD = "a new password from the reset link";

test.describe("password reset and change password", () => {
  test("request a reset, open the email in Mailpit, set a new password and sign in", async ({ page }) => {
    const member = newMember();
    await signUp(page.request, member);
    await page.context().clearCookies();

    await page.goto("/sign-in");
    await page.getByRole("link", { name: "Forgot your password?" }).click();
    await page.getByLabel("Email").fill(member.email);
    await page.getByRole("button", { name: "Send reset link" }).click();
    await expect(page.getByRole("status")).toHaveText(
      "If that email is registered, a reset link is on its way. Check your inbox.",
    );

    const email = await latestEmailTo(page.request, member.email);
    expect(email.Subject).toBe("Reset your RAG Agent Studio password");
    const resetLink = linkPath(email.Text, "/reset-password");
    await page.goto(resetLink);
    await page.getByLabel("New password", { exact: true }).fill(NEW_PASSWORD);
    await page.getByRole("button", { name: "Set new password" }).click();
    await expect(page.getByRole("status")).toContainText("Your password has been reset");

    await page.getByRole("link", { name: "Sign in with your new password" }).click();
    await page.getByLabel("Email").fill(member.email);
    await page.getByLabel("Password").fill(NEW_PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();

    // The link worked once; opening it again is refused.
    await page.goto(resetLink);
    await page.getByLabel("New password", { exact: true }).fill("one more new password");
    await page.getByRole("button", { name: "Set new password" }).click();
    await expect(page.getByRole("alert")).toContainText("This reset link is invalid or has expired.");
  });

  test("a Member renames themselves and changes their password, ending their other sessions", async ({
    signedInPage: page,
    member,
    browser,
  }) => {
    const otherDevice = await browser.newContext();
    const otherPage = await otherDevice.newPage();
    const signIn = await otherPage.request.post("/api/auth/sign-in", {
      data: { email: member.email, password: member.password },
    });
    expect(signIn.ok()).toBe(true);

    await page.goto("/");
    await openSection(page, "Account", "Profile");
    await expect(page.getByRole("heading", { name: "Profile" })).toBeVisible();
    const nameForm = page.getByRole("form", { name: "Your name" });
    await nameForm.getByLabel("Name").fill("Renamed Member");
    await nameForm.getByRole("button", { name: "Save name" }).click();
    await expect(nameForm.getByRole("status")).toHaveText("Name saved.");
    await expect(page.getByRole("banner").getByText("Renamed Member")).toBeVisible();

    const passwordForm = page.getByRole("form", { name: "Change password" });
    await passwordForm.getByLabel("Current password").fill(member.password);
    await passwordForm.getByLabel("New password").fill(NEW_PASSWORD);
    await passwordForm.getByRole("button", { name: "Change password" }).click();
    await expect(passwordForm.getByRole("status")).toHaveText(
      "Password changed. Your other sessions have been signed out.",
    );

    expect((await otherPage.request.get("/api/auth/me")).status()).toBe(401);
    await page.reload();
    await expect(page.getByRole("heading", { name: "Profile" })).toBeVisible();
    await otherDevice.close();
  });
});

test.describe("accessibility", () => {
  for (const path of ["/forgot-password", "/reset-password?token=example"]) {
    test(`${path} has no WCAG 2.2 AA violations`, async ({ page, makeAxeBuilder }) => {
      await page.goto(path);
      await expect(page.getByRole("button")).toBeVisible();
      const results = await makeAxeBuilder().analyze();
      expect(results.violations).toEqual([]);
    });
  }

  test("the Profile page has no WCAG 2.2 AA violations", async ({ signedInPage, makeAxeBuilder }) => {
    await signedInPage.goto("/");
    await openSection(signedInPage, "Account", "Profile");
    await expect(signedInPage.getByRole("heading", { name: "Profile" })).toBeVisible();
    const results = await makeAxeBuilder().analyze();
    expect(results.violations).toEqual([]);
  });
});
