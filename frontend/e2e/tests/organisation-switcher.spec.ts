import { expect, test } from "../fixtures";
import { newMember, signInAs, signUp } from "../fixtures/auth";

test.describe("organisation switcher", () => {
  test("a Member of two Organisations switches between them, and the choice survives reloads and sign-ins", async ({
    signedInPage: page,
    member,
    browser,
    makeAxeBuilder,
  }) => {
    // Another Owner invites the Member into a second Organisation as an Editor, by copied link.
    const otherOwner = newMember({ organisationName: `Second Organisation ${member.name.slice(-8)}` });
    const otherContext = await browser.newContext();
    await signUp(otherContext.request, otherOwner);
    const me = (await (await otherContext.request.get("/api/auth/me")).json()) as {
      organisations: { id: string }[];
    };
    const secondId = me.organisations[0]?.id ?? "";
    const invited = await otherContext.request.post(`/api/organisations/${secondId}/invites`, {
      data: { email: member.email, role: "editor", send_email: false },
    });
    expect(invited.status()).toBe(201);
    const { link } = (await invited.json()) as { link: string };
    const token = new URL(link).searchParams.get("token") ?? "";
    expect((await page.request.post("/api/invites/accept", { data: { token } })).status()).toBe(200);

    await page.goto("/");
    const switcher = page.getByRole("combobox", { name: "Organisation" });
    await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
    await expect(switcher.getByRole("option")).toHaveText([member.organisationName, otherOwner.organisationName]);
    await expect(switcher).toHaveValue(/.+/);
    const firstId = await switcher.inputValue();
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    // As an Owner here, the Member sees the Members tab.
    await page.getByRole("link", { name: "Organisation settings" }).click();
    await expect(page.getByRole("navigation", { name: "Organisation settings" }).getByRole("link", { name: "Members" })).toBeVisible();

    await switcher.selectOption({ label: otherOwner.organisationName });

    await expect(page).toHaveURL(new RegExp(`/organisations/${secondId}/projects$`));
    await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
    // As an Editor in the second Organisation, nothing from the first one's Owner areas is shown.
    await page.getByRole("link", { name: "Organisation settings" }).click();
    const tabs = page.getByRole("navigation", { name: "Organisation settings" });
    await expect(tabs.getByRole("link", { name: "General" })).toBeVisible();
    await expect(tabs.getByRole("link", { name: "Members" })).toHaveCount(0);
    // Its Members page, opened by address, is refused to an Editor.
    await page.goto(`/organisations/${secondId}/settings/members`);
    await expect(page.getByText(/Only Owners/)).toBeVisible();
    await expect(page.getByRole("table", { name: "Pending invites" })).toHaveCount(0);

    // A reload keeps the second Organisation, and so does opening the Studio afresh.
    await page.reload();
    await expect(switcher).toHaveValue(secondId);
    await page.goto("/");
    await expect(page).toHaveURL(new RegExp(`/organisations/${secondId}/projects$`));
    await expect(switcher).toHaveValue(secondId);

    // A new sign-in, in a new browser, opens it too.
    const laterContext = await browser.newContext();
    const later = await laterContext.newPage();
    await signInAs(later, member);
    await later.goto("/");
    await expect(later).toHaveURL(new RegExp(`/organisations/${secondId}/projects$`));

    // Switching back is remembered as well.
    await later.getByRole("combobox", { name: "Organisation" }).selectOption({ label: member.organisationName });
    await expect(later).toHaveURL(new RegExp(`/organisations/${firstId}/projects$`));
    await page.goto("/");
    await expect(page).toHaveURL(new RegExp(`/organisations/${firstId}/projects$`));

    await laterContext.close();
    await otherContext.close();
  });
});
