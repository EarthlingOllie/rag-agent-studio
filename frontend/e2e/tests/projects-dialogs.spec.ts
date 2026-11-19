import type { Browser, Locator, Page, Route } from "@playwright/test";

import { expect, test } from "../fixtures";
import { type MemberCredentials, newMember } from "../fixtures/auth";
import { openSection } from "../fixtures/navigation";

/** Today's date as the Studio prints it (`2026-11-18`, UTC), read before and after an action. */
function utcDay(offsetDays = 0): string {
  return new Date(Date.now() + offsetDays * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
}

async function openProjects(page: Page) {
  await page.goto("/");
  await openSection(page, "Organisation sections", "Projects");
  await expect(page.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible();
}

function newProjectButton(page: Page) {
  return page.getByRole("button", { name: "New Project" });
}

function shown(page: Page, which: "Active" | "Archived") {
  return page.getByRole("radiogroup", { name: "Projects shown" }).getByRole("radio", { name: which }).click();
}

/** A toast: the polite status region holding the confirmation. */
function toast(page: Page, message: string) {
  return page.getByRole("status").filter({ hasText: message });
}

async function createProject(page: Page, name: string, description = "") {
  await openProjects(page);
  await newProjectButton(page).click();
  const form = page.getByRole("form", { name: "New Project" });
  await form.getByLabel("Name").fill(name);
  await form.getByLabel("Description").fill(description);
  await form.getByRole("button", { name: "Create Project" }).click();
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
}

async function archiveOpenProject(page: Page, name: string) {
  await page.getByRole("button", { name: "More Project actions" }).click();
  await page.getByRole("menu", { name: "Project actions" }).getByRole("menuitem", { name: "Archive" }).click();
  await page.getByRole("button", { name: `Yes, archive ${name}` }).click();
  await expect(page.getByText(/This Project is archived/)).toBeVisible();
}

async function openMembers(page: Page) {
  await page.goto("/");
  await openSection(page, "Organisation sections", "Settings");
  await openSection(page, "Organisation settings", "Members");
  await expect(page.getByRole("table", { name: "Members" })).toBeVisible();
}

async function openInviteDialog(page: Page) {
  await page.getByRole("button", { name: "Invite someone" }).click();
  const form = page.getByRole("form", { name: "Invite someone" });
  await expect(form).toBeVisible();
  return form;
}

/** Invites by copied link only (no email), as an Editor. */
async function inviteByLink(page: Page, email: string) {
  const form = await openInviteDialog(page);
  await form.getByLabel("Email", { exact: true }).fill(email);
  await form.getByLabel("Role").selectOption("Editor");
  await form.getByLabel("Email the invite link").uncheck();
  await form.getByRole("button", { name: "Invite" }).click();
  return form;
}

/** The Owner invites a new person with a copied link; they create an account in their own browser. */
async function inviteNewEditor(owner: Page, browser: Browser, person: MemberCredentials): Promise<Page> {
  await openMembers(owner);
  await inviteByLink(owner, person.email);
  const link = new URL(await owner.getByLabel(`Invite link for ${person.email}`).inputValue());
  const page = await (await browser.newContext()).newPage();
  await page.goto(link.pathname + link.search);
  await page.getByLabel("Your name").fill(person.name);
  await page.getByLabel("Password").fill(person.password);
  await page.getByRole("button", { name: "Create account and join" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible();
  return page;
}

/** Matches the Organisation's list of active Projects (not one Project, not the archived list). */
function isActiveProjectsList(url: URL) {
  return /\/api\/organisations\/[^/]+\/projects$/.test(url.pathname) && url.searchParams.get("archived") === "false";
}

/** The relative luminance of an `#rrggbb` or `rgb(r, g, b)` colour (WCAG 2.2). */
function luminance(colour: string): number {
  const hex = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(colour);
  const rgb = /rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(colour);
  const parts = (hex ? hex.slice(1).map((part) => Number.parseInt(part, 16)) : rgb?.slice(1).map(Number)) ?? [];
  expect(parts, `a colour: ${colour}`).toHaveLength(3);
  const [r, g, b] = parts.map((value) => {
    const channel = value / 255;
    return channel <= 0.039_28 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (light + 0.05) / (dark + 0.05);
}

/** The colour a select's chevron is stroked in, and the field it is drawn on. */
function chevronOn(select: Locator) {
  return select.evaluate((element) => {
    const style = getComputedStyle(element);
    const svg = decodeURIComponent(style.backgroundImage);
    return { stroke: /stroke='([^']+)'/.exec(svg)?.[1] ?? "", field: style.backgroundColor, opacity: style.opacity };
  });
}

test.describe("Projects list", () => {
  test("a Member opens Projects and reads a title with a one-line description of what a Project is for", async ({
    signedInPage: page,
  }) => {
    await openProjects(page);
    const header = page.getByRole("region", { name: "Projects" });
    await expect(header.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible();
    await expect(header.getByText("Each Project holds the Documents its Agents answer from.", { exact: true })).toBeVisible();
  });

  test("a Project's name is an un-underlined link styled like an Agent's name in the Agents list", async ({
    signedInPage: page,
  }) => {
    await createProject(page, "P5 link style");
    await openSection(page, "Project sections", "Agents");
    await page.getByRole("button", { name: "New Agent" }).click();
    await page.getByRole("form", { name: "New Agent" }).getByLabel("Name").fill("P5 helper");
    await page.getByRole("form", { name: "New Agent" }).getByRole("button", { name: "Create Agent" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "P5 helper" })).toBeVisible({ timeout: 15_000 });
    await openSection(page, "Project sections", "Agents");
    const agentLink = page.getByRole("table", { name: "Agents" }).getByRole("link", { name: "P5 helper" });

    const look = (link: Locator) =>
      link.evaluate((element) => {
        const style = getComputedStyle(element);
        return { underline: style.textDecorationLine, colour: style.color, weight: style.fontWeight, size: style.fontSize };
      });
    const agentLook = await look(agentLink);

    await openProjects(page);
    const projectLink = page.getByRole("table", { name: "Projects" }).getByRole("link", { name: "P5 link style" });
    const projectLook = await look(projectLink);
    expect(projectLook.underline).toBe("none");
    expect(projectLook).toEqual(agentLook);
  });

  test("a long description is kept to one line, so its row is as tall as a short one", async ({ signedInPage: page }) => {
    const long = `P5 long description ${"that keeps going and going ".repeat(20)}until the end.`;
    await createProject(page, "P5 short row", "Short.");
    await createProject(page, "P5 long row", long);
    await openProjects(page);
    const projects = page.getByRole("table", { name: "Projects" });
    const shortRow = projects.getByRole("row").filter({ hasText: "P5 short row" });
    const longRow = projects.getByRole("row").filter({ hasText: "P5 long row" });
    const description = longRow.getByRole("cell").nth(1).locator("span");

    await expect(description).toHaveAttribute("title", long);
    const clipped = await description.evaluate((element) => ({
      overflowing: element.scrollWidth > element.clientWidth,
      lines: Math.round(element.getBoundingClientRect().height / Number.parseFloat(getComputedStyle(element).lineHeight)),
    }));
    expect(clipped).toEqual({ overflowing: true, lines: 1 });
    const heights = await Promise.all([shortRow, longRow].map(async (row) => (await row.boundingBox())?.height));
    // Within a pixel of rounding; a second line of text would add ~20px.
    expect(Math.abs((heights[1] ?? 0) - (heights[0] ?? 0))).toBeLessThanOrEqual(1);
  });

  test("an Owner archives a Project and finds it in the Archived list with the date it was archived", async ({
    signedInPage: page,
  }) => {
    await createProject(page, "P5 archived dated");
    const before = utcDay();
    await archiveOpenProject(page, "P5 archived dated");
    const after = utcDay();
    await openProjects(page);
    await shown(page, "Archived");
    const archived = page.getByRole("table", { name: "Archived Projects" });
    await expect(archived.getByRole("columnheader", { name: "Archived" })).toBeVisible();
    const cells = archived.getByRole("row").filter({ hasText: "P5 archived dated" }).getByRole("cell");
    await expect(cells.nth(0)).toHaveText("P5 archived dated");
    await expect(cells.nth(1)).toHaveText(new RegExp(`^(${before}|${after})$`));
  });

  test("an Editor looking at archived Projects is told only Owners can restore them, and is offered no Restore", async ({
    signedInPage: page,
    browser,
  }) => {
    await createProject(page, "P5 kept by owner");
    await archiveOpenProject(page, "P5 kept by owner");
    const editorPage = await inviteNewEditor(page, browser, newMember({ name: "P5 Editor" }));

    await shown(editorPage, "Archived");
    await expect(editorPage.getByRole("table", { name: "Archived Projects" }).getByRole("link", { name: "P5 kept by owner" })).toBeVisible();
    await expect(editorPage.getByText("Only Owners can restore them.")).toBeVisible();
    await expect(editorPage.getByRole("button", { name: /^Restore/ })).toHaveCount(0);
    await editorPage.context().close();

    // The Owner, on the same view, is offered Restore instead.
    await openProjects(page);
    await shown(page, "Archived");
    await expect(page.getByText("Restore one to bring it back.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Restore P5 kept by owner" })).toBeVisible();
  });

  test("a Member sees a loading placeholder while the Projects load, then the list", async ({ signedInPage: page }) => {
    let release: () => void = () => undefined;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route(isActiveProjectsList, async (route: Route) => {
      await held;
      await route.continue();
    });
    await page.goto("/");
    await openSection(page, "Organisation sections", "Projects");
    const placeholder = page.getByRole("status", { name: "Loading Projects" });
    await expect(placeholder).toBeVisible();
    await expect(placeholder).toHaveAttribute("aria-busy", "true");
    await expect(page.getByRole("heading", { name: "No Projects yet" })).toHaveCount(0);

    release();
    await expect(page.getByRole("heading", { name: "No Projects yet" })).toBeVisible();
    await expect(placeholder).toHaveCount(0);
  });

  test("a Member is shown a clear error, with what to do next, when the Projects can't be loaded", async ({
    signedInPage: page,
  }) => {
    await page.route(isActiveProjectsList, (route: Route) =>
      route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "Boom" }) }),
    );
    await page.goto("/");
    await openSection(page, "Organisation sections", "Projects");
    // The list retries a few times before it gives up.
    await expect(page.getByRole("heading", { name: "The Projects could not be loaded" })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText("Try again shortly.")).toBeVisible();
    await expect(page.getByRole("status", { name: "Loading Projects" })).toHaveCount(0);
    await expect(page.getByRole("table", { name: "Projects" })).toHaveCount(0);
  });

  test("empty Project lists say what is happening and what to do next", async ({ signedInPage: page }) => {
    await openProjects(page);
    await expect(page.getByRole("heading", { name: "No Projects yet" })).toBeVisible();
    await expect(page.getByText("Create one with New Project to start collecting knowledge for a purpose.")).toBeVisible();
    await expect(newProjectButton(page)).toBeVisible();
    await shown(page, "Archived");
    await expect(page.getByRole("heading", { name: "No archived Projects" })).toBeVisible();
    await expect(page.getByText("A Project you archive is kept here, with its Documents and Agents.")).toBeVisible();
  });
});

test.describe("New Project and Edit details", () => {
  test("a Member who gives a blank name sees why inside the dialog, keeps what they typed, and then creates it", async ({
    signedInPage: page,
  }) => {
    await openProjects(page);
    await newProjectButton(page).click();
    const form = page.getByRole("form", { name: "New Project" });
    await form.getByLabel("Name").fill("   ");
    await form.getByLabel("Description").fill("P5 kept description");
    await form.getByRole("button", { name: "Create Project" }).click();

    await expect(form.getByRole("alert")).toHaveText("Give the Project a name of up to 200 characters, and a description of up to 2,000.");
    await expect(form.getByLabel("Name")).toHaveValue("   ");
    await expect(form.getByLabel("Description")).toHaveValue("P5 kept description");
    await expect(page.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible();

    await form.getByLabel("Name").fill("P5 fixed name");
    await form.getByRole("button", { name: "Create Project" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "P5 fixed name" })).toBeVisible();
    await expect(page.getByText("P5 kept description")).toBeVisible();
  });

  for (const how of ["Cancel", "Escape"] as const) {
    test(`a Member backs out of New Project with ${how}: nothing is created and focus returns to New Project`, async ({
      signedInPage: page,
    }) => {
      await openProjects(page);
      await expect(page.getByRole("heading", { name: "No Projects yet" })).toBeVisible();
      await newProjectButton(page).click();
      const form = page.getByRole("form", { name: "New Project" });
      await form.getByLabel("Name").fill(`P5 not created ${how}`);
      if (how === "Cancel") await form.getByRole("button", { name: "Cancel" }).click();
      else await page.keyboard.press("Escape");

      await expect(form).toHaveCount(0);
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(newProjectButton(page)).toBeFocused();
      await expect(page.getByRole("heading", { name: "No Projects yet" })).toBeVisible();
      await page.reload();
      await expect(page.getByRole("heading", { name: "No Projects yet" })).toBeVisible();
    });
  }

  test("a Member looking at archived Projects is not offered New Project", async ({ signedInPage: page }) => {
    await openProjects(page);
    await expect(newProjectButton(page)).toBeVisible();
    await shown(page, "Archived");
    await expect(page.getByRole("heading", { name: "No archived Projects" })).toBeVisible();
    await expect(newProjectButton(page)).toHaveCount(0);
    await shown(page, "Active");
    await expect(newProjectButton(page)).toBeVisible();
  });

  test("a Member opens Edit details on the current name and description, the button stays put, and a toast confirms the save", async ({
    signedInPage: page,
  }) => {
    await createProject(page, "P5 before edit", "P5 original description");
    const edit = page.getByRole("button", { name: "Edit details" });
    const where = await edit.boundingBox();
    await edit.click();
    const details = page.getByRole("form", { name: "Project details" });
    await expect(details.getByLabel("Name")).toHaveValue("P5 before edit");
    await expect(details.getByLabel("Description")).toHaveValue("P5 original description");

    // While editing the header doesn't rearrange: Edit details is where it was.
    await details.getByLabel("Name").fill("P5 after edit with a much longer name than before");
    expect(await edit.boundingBox()).toEqual(where);

    await details.getByRole("button", { name: "Save" }).click();
    await expect(details).toHaveCount(0);
    await expect(toast(page, "Project details saved")).toBeVisible();
    await expect(page.getByRole("heading", { level: 1, name: "P5 after edit with a much longer name than before" })).toBeVisible();
    await expect(page.getByText("P5 original description")).toBeVisible();
  });

  test("an Owner archives a Project, sees a short confirmation and can Undo it", async ({ signedInPage: page }) => {
    test.fixme(true, "11.16: no change in the Studio offers Undo — the Toast supports onUndo but no caller passes it; archiving a Project shows no toast at all");
    await createProject(page, "P5 undo archive");
    await archiveOpenProject(page, "P5 undo archive");
    await expect(toast(page, "Archived P5 undo archive.")).toBeVisible();
    await page.getByRole("button", { name: "Undo" }).click();
    await expect(page.getByText(/This Project is archived/)).toHaveCount(0);
    await openProjects(page);
    await expect(page.getByRole("table", { name: "Projects" }).getByRole("link", { name: "P5 undo archive" })).toBeVisible();
  });
});

test.describe("Invite someone", () => {
  test("an Owner invites someone: the dialog closes, a toast confirms it, and the link and its expiry stay on the page", async ({
    signedInPage: page,
  }) => {
    const person = newMember({ name: "P5 Invitee" });
    await openMembers(page);
    const before = utcDay(7);
    const form = await inviteByLink(page, person.email);
    const after = utcDay(7);

    await expect(form).toHaveCount(0);
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(toast(page, `Invited ${person.email}.`)).toBeVisible();

    const panel = page.getByRole("region", { name: "New invite" });
    await expect(panel).toContainText(`Copy the link and send it to ${person.email}.`);
    const link = new URL(await panel.getByLabel(`Invite link for ${person.email}`).inputValue());
    expect(link.pathname).toBe("/accept-invite");
    expect(link.searchParams.get("token")?.length ?? 0).toBeGreaterThan(10);
    await expect(panel.getByRole("button", { name: "Copy link" })).toBeVisible();
    // Invites last 7 days.
    await expect(panel).toContainText(new RegExp(`The link works once and expires on (${before}|${after})\\.`));
  });

  test("an Owner is told inside the dialog about an invalid email or an existing Member, and keeps what they typed", async ({
    signedInPage: page,
    member,
  }) => {
    await openMembers(page);
    const form = await openInviteDialog(page);
    const email = form.getByLabel("Email", { exact: true });

    // Accepted by the browser, refused by the Studio: no dot in the domain.
    await email.fill("p5-nobody@localhost");
    await form.getByLabel("Role").selectOption("Owner");
    await form.getByRole("button", { name: "Invite" }).click();
    await expect(form.getByRole("alert")).toHaveText("Enter a valid email address.");
    await expect(email).toHaveValue("p5-nobody@localhost");
    await expect(form.getByLabel("Role")).toHaveValue("owner");

    await email.fill(member.email);
    await form.getByRole("button", { name: "Invite" }).click();
    await expect(form.getByRole("alert")).toHaveText("That person is already a Member of this Organisation");
    await expect(email).toHaveValue(member.email);
    await expect(page.getByRole("region", { name: "New invite" })).toHaveCount(0);
    await expect(page.getByText("No pending invites.")).toBeVisible();
  });

  test("an Owner takes a new link from a pending invite and gets the same copy-link panel", async ({ signedInPage: page }) => {
    const person = newMember({ name: "P5 Renewed" });
    await openMembers(page);
    await inviteByLink(page, person.email);
    const panel = page.getByRole("region", { name: "New invite" });
    const first = await panel.getByLabel(`Invite link for ${person.email}`).inputValue();

    // Start from a page without the panel, as when coming back later.
    await page.reload();
    await expect(page.getByRole("table", { name: "Members" })).toBeVisible();
    await expect(panel).toHaveCount(0);
    const before = utcDay(7);
    await page.getByRole("table", { name: "Pending invites" }).getByRole("button", { name: `New link for ${person.email}` }).click();
    const after = utcDay(7);

    await expect(toast(page, `New invite link for ${person.email}.`)).toBeVisible();
    await expect(panel).toContainText(`Copy the link and send it to ${person.email}.`);
    const renewed = await panel.getByLabel(`Invite link for ${person.email}`).inputValue();
    expect(new URL(renewed).pathname).toBe("/accept-invite");
    expect(renewed).not.toBe(first);
    await expect(panel.getByRole("button", { name: "Copy link" })).toBeVisible();
    await expect(panel).toContainText(new RegExp(`The link works once and expires on (${before}|${after})\\.`));
  });
});

test.describe("Selects", () => {
  test("in the dark Appearance a select's chevron stands out from its field", async ({ signedInPage: page, member }) => {
    await page.emulateMedia({ colorScheme: "dark" });
    await openMembers(page);
    const form = await openInviteDialog(page);
    for (const select of [form.getByLabel("Role"), page.getByLabel(`Role for ${member.name}`)]) {
      const { stroke, field } = await chevronOn(select);
      expect(luminance(field), `a dark field: ${field}`).toBeLessThan(0.05);
      // WCAG 2.2 non-text contrast: at least 3:1 against the field it sits on.
      expect(contrast(stroke, field), `${stroke} on ${field}`).toBeGreaterThanOrEqual(3);
    }
  });

  test("a disabled select dims its chevron with the field", async ({ signedInPage: page }) => {
    await createProject(page, "P5 disabled select");
    await openSection(page, "Project sections", "Agents");
    await page.getByRole("button", { name: "New Agent" }).click();
    await page.getByRole("form", { name: "New Agent" }).getByLabel("Name").fill("P5 archived helper");
    await page.getByRole("form", { name: "New Agent" }).getByRole("button", { name: "Create Agent" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "P5 archived helper" })).toBeVisible({ timeout: 15_000 });

    const guardrails = page.getByRole("complementary", { name: "Configuration" }).locator("details").filter({
      has: page.locator('fieldset[aria-label="Guardrails"]'),
    });
    const openGuardrails = async () => {
      if (!(await guardrails.evaluate((element) => (element as HTMLDetailsElement).open))) await guardrails.locator("summary").click();
    };
    await openGuardrails();
    const select = page.getByLabel("Input Guardrail mode");
    await expect(select).toBeEnabled();
    const enabled = await chevronOn(select);
    expect(enabled.opacity).toBe("1");

    await page.getByRole("button", { name: "More Agent actions" }).click();
    await page.getByRole("menu", { name: "Agent actions" }).getByRole("menuitem", { name: "Archive" }).click();
    await page.getByRole("alertdialog", { name: "Archive P5 archived helper?" }).getByRole("button", { name: "Yes, archive P5 archived helper" }).click();
    await expect(page.getByRole("status", { name: "Archived" })).toContainText("This Agent is archived.");
    await openGuardrails();
    await expect(select).toBeDisabled();
    const disabled = await chevronOn(select);
    // The chevron is still drawn, and the whole field (chevron included) is dimmed.
    expect(disabled.stroke).toBe(enabled.stroke);
    expect(Number(disabled.opacity)).toBeLessThan(1);
    expect(Number(disabled.opacity)).toBeGreaterThan(0);
  });
});
