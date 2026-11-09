import { expect, test } from "../fixtures";
import { newMember, signInAs, signUp } from "../fixtures/auth";
import { menuButton, openSection, sectionNames } from "../fixtures/navigation";

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
    const switcher = menuButton(page, "Organisations");
    await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
    expect(await sectionNames(page, "Organisations")).toEqual([member.organisationName, otherOwner.organisationName]);
    await expect(switcher).toHaveAccessibleName(`${member.organisationName}, Organisations`);
    const firstId = /\/organisations\/([^/]+)\//.exec(page.url())?.[1] ?? "";
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    // As an Owner here, the Member sees the Members tab.
    await openSection(page, "Organisation sections", "Settings");
    expect(await sectionNames(page, "Organisation settings")).toContain("Members");

    await openSection(page, "Organisations", otherOwner.organisationName);

    await expect(page).toHaveURL(new RegExp(`/organisations/${secondId}/projects$`));
    await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
    // As an Editor in the second Organisation, nothing from the first one's Owner areas is shown.
    await openSection(page, "Organisation sections", "Settings");
    const sections = await sectionNames(page, "Organisation settings");
    expect(sections).toContain("General");
    expect(sections).not.toContain("Members");
    // Its Members page, opened by address, is refused to an Editor.
    await page.goto(`/organisations/${secondId}/settings/members`);
    await expect(page.getByText(/Only Owners/)).toBeVisible();
    await expect(page.getByRole("table", { name: "Pending invites" })).toHaveCount(0);

    // A reload keeps the second Organisation, and so does opening the Studio afresh.
    await page.reload();
    await expect(switcher).toHaveAccessibleName(`${otherOwner.organisationName}, Organisations`);
    await page.goto("/");
    await expect(page).toHaveURL(new RegExp(`/organisations/${secondId}/projects$`));
    await expect(switcher).toHaveAccessibleName(`${otherOwner.organisationName}, Organisations`);

    // A new sign-in, in a new browser, opens it too.
    const laterContext = await browser.newContext();
    const later = await laterContext.newPage();
    await signInAs(later, member);
    await later.goto("/");
    await expect(later).toHaveURL(new RegExp(`/organisations/${secondId}/projects$`));

    // Switching back is remembered as well.
    await openSection(later, "Organisations", member.organisationName);
    await expect(later).toHaveURL(new RegExp(`/organisations/${firstId}/projects$`));
    await page.goto("/");
    await expect(page).toHaveURL(new RegExp(`/organisations/${firstId}/projects$`));

    await laterContext.close();
    await otherContext.close();
  });
});
