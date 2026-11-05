import { newMember, signIn, signInAs, signUp } from "../fixtures/auth";
import { expect, test } from "./test";

test.describe("signed-in page helpers", () => {
  test("signedInPage is signed in as a newly signed-up Member", async ({ signedInPage, member }) => {
    await signedInPage.goto("/whoami");
    await expect(signedInPage.getByRole("heading")).toHaveText(`Signed in as ${member.email}`);
  });

  test("an ordinary page stays signed out", async ({ page }) => {
    await page.goto("/whoami");
    await expect(page.getByRole("heading")).toHaveText("Signed out");
  });

  test("signInAs signs an existing Member into a page", async ({ page }) => {
    const member = newMember();
    await signUp(page.request, member);
    await signInAs(page, member);
    await page.goto("/whoami");
    await expect(page.getByRole("heading")).toHaveText(`Signed in as ${member.email}`);
  });

  test("a failed auth call names the route and status", async ({ page }) => {
    const member = newMember();
    await signUp(page.request, member);
    await expect(signUp(page.request, member)).rejects.toThrow(/POST \/api\/auth\/sign-up answered 409: .*already registered/);
    await expect(signIn(page.request, { ...member, password: "wrong password" })).rejects.toThrow(
      /POST \/api\/auth\/sign-in answered 401/,
    );
  });

  test("each new Member has a unique email", () => {
    const emails = new Set(Array.from({ length: 50 }, () => newMember().email));
    expect(emails.size).toBe(50);
    expect(newMember({ name: "Ada" }).name).toBe("Ada");
  });
});
