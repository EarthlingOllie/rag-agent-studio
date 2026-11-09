import { expect, test } from "../fixtures";
import { newMember, signUp } from "../fixtures/auth";
import { menuButton, openSection } from "../fixtures/navigation";

test.describe("sign up, sign in, sign out", () => {
  test("a visitor signs up, sees the signed-in shell and signs out", async ({ page, member }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    await page.getByRole("link", { name: "Create an account" }).click();

    await page.getByLabel("Your name").fill(member.name);
    await page.getByLabel("Email").fill(member.email);
    await page.getByLabel("Password").fill(member.password);
    await page.getByLabel("Organisation name").fill(member.organisationName);
    await page.getByRole("button", { name: "Create account" }).click();

    await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
    await expect(page.getByText(member.organisationName)).toBeVisible();
    await expect(menuButton(page, "Account")).toHaveAccessibleName(`${member.name}, Account`);
    await openSection(page, "Organisation sections", "Settings");
    await expect(page.getByRole("heading", { name: "Organisation settings" })).toBeVisible();

    const cookies = await page.context().cookies();
    const session = cookies.find((cookie) => cookie.name === "studio_session");
    expect(session).toMatchObject({ httpOnly: true, secure: true, sameSite: "Lax" });

    await openSection(page, "Account", "Sign out");

    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    // The server ended the session: the old cookie no longer signs anyone in.
    const replay = await page.request.get("/api/auth/me", {
      headers: { cookie: `studio_session=${session?.value ?? ""}` },
    });
    expect(replay.status()).toBe(401);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  });

  test("a Member signs back in after a wrong password", async ({ page }) => {
    const member = newMember();
    await signUp(page.request, member);
    await page.context().clearCookies();

    await page.goto("/sign-in");
    await page.getByLabel("Email").fill(member.email);
    await page.getByLabel("Password").fill("not the password at all");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("alert")).toHaveText("Email or password is incorrect.");

    await page.getByLabel("Password").fill(member.password);
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
    await expect(page.getByText(member.organisationName)).toBeVisible();
  });

  test("the signedInPage fixture opens the Member's Organisation", async ({ signedInPage, member }) => {
    await signedInPage.goto("/");

    await expect(signedInPage.getByRole("heading", { name: "Projects" })).toBeVisible();
    await expect(signedInPage.getByText(member.organisationName)).toBeVisible();
  });
});

test.describe("accessibility", () => {
  for (const path of ["/sign-in", "/sign-up"]) {
    test(`${path} has no WCAG 2.2 AA violations`, async ({ page, makeAxeBuilder }) => {
      await page.goto(path);
      await expect(page.getByRole("button")).toBeVisible();
      const results = await makeAxeBuilder().analyze();
      expect(results.violations).toEqual([]);
    });
  }

  test("the signed-in shell has no WCAG 2.2 AA violations", async ({ signedInPage, makeAxeBuilder }) => {
    await signedInPage.goto("/");
    await expect(signedInPage.getByRole("heading", { name: "Projects" })).toBeVisible();
    const results = await makeAxeBuilder().analyze();
    expect(results.violations).toEqual([]);
  });
});
