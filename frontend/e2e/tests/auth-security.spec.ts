import type { APIRequestContext, Browser, Locator, Page } from "@playwright/test";

import { expect, test } from "../fixtures";
import { openSettings } from "../fixtures/agent";
import { API_URL, emailCount, expireLink, linkToken } from "../fixtures/auth-security";
import { type MemberCredentials, newMember, signInAs, signUp } from "../fixtures/auth";
import { latestEmailTo, linkPath } from "../fixtures/mailpit";
import { openSection } from "../fixtures/navigation";
import { totpCode, totpStep } from "../fixtures/totp";

const INCORRECT = "Email or password is incorrect.";
const RESET_SENT = "If that email is registered, a reset link is on its way. Check your inbox.";
const RESET_EXPIRED = "This reset link is invalid or has expired.";
const NEW_PASSWORD = "a brand new password for auth security";

// `make seed` runs before the suite; these are the accounts it prints. Only read here.
const SEED_EDITOR = { email: "editor@northwind.example", password: "northwind-editor-demo" };

async function organisationId(request: APIRequestContext): Promise<string> {
  const me = (await (await request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
  return me.organisations[0]?.id ?? "";
}

/** A sign-in sent straight to the API, so it doesn't count against the Studio proxy's IP. */
async function directSignIn(request: APIRequestContext, email: string, password: string) {
  return request.post(`${API_URL}/api/auth/sign-in`, { data: { email, password } });
}

/**
 * A sign-in straight at the API once no earlier failure makes it wait. Earlier runs' failures from
 * this host can make the IP's attempts wait a little; refused attempts aren't counted.
 */
async function checkedSignIn(request: APIRequestContext, email: string, password: string) {
  let response = await directSignIn(request, email, password);
  await expect
    .poll(
      async () => {
        if (response.status() === 429) response = await directSignIn(request, email, password);
        return response.status();
      },
      { intervals: [500], timeout: 45_000 },
    )
    .not.toBe(429);
  return response;
}

/**
 * Fails one sign-in for `email` straight at the API: while earlier failures make it wait, its
 * attempts are refused (and not counted) until the wait is over and a wrong password is checked.
 */
async function failOneSignIn(request: APIRequestContext, email: string): Promise<void> {
  await expect
    .poll(async () => (await directSignIn(request, email, "definitely not the password")).status(), {
      intervals: [250],
      timeout: 45_000,
    })
    .toBe(401);
}

/** Signs in through the sign-in page of a fresh, signed-out browser. */
async function signInThroughPage(page: Page, email: string, password: string): Promise<void> {
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

async function openAudit(page: Page) {
  await page.goto("/");
  await openSection(page, "Organisation sections", "Settings");
  await openSection(page, "Organisation settings", "Audit");
  await expect(page.getByRole("table", { name: "Audit Events" })).toBeVisible();
}

function auditRows(page: Page, action: string) {
  return page.getByRole("table", { name: "Audit Events" }).getByRole("row").filter({ hasText: action });
}

/** An Audit Event row's Before or After values, as shown in its column. */
async function values(row: Locator, column: "before" | "after"): Promise<unknown> {
  return JSON.parse((await row.getByRole("cell").nth(column === "before" ? 4 : 5).textContent()) ?? "null") as unknown;
}

/** Invites `person` as an Editor with a copied link; they join with a new account through the API. */
async function addEditor(owner: Page, browser: Browser, person: MemberCredentials): Promise<Page> {
  const invited = await owner.request.post(`/api/organisations/${await organisationId(owner.request)}/invites`, {
    data: { email: person.email, role: "editor", send_email: false },
  });
  expect(invited.status()).toBe(201);
  const token = linkToken(((await invited.json()) as { link: string }).link);
  const page = await (await browser.newContext()).newPage();
  const joined = await page.request.post("/api/invites/sign-up", { data: { token, name: person.name, password: person.password } });
  expect(joined.status()).toBe(201);
  return page;
}

async function requestReset(page: Page, email: string): Promise<string> {
  await page.goto("/forgot-password");
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Send reset link" }).click();
  await expect(page.getByRole("status")).toHaveText(RESET_SENT);
  return linkPath((await latestEmailTo(page.request, email)).Text, "/reset-password");
}

test.describe("Sign-in hardening", () => {
  test("repeated failed sign-ins are slowed, then lock the account out even with the right password, and the lockout is audited", async ({
    signedInPage: owner,
    member,
    browser,
  }) => {
    // Seven waits of 1, 2, 4, 8, 16, 30 and 30 seconds stand between the 3rd and the 10th failure;
    // runs repeated within 15 minutes add the host IP's own waits of up to 30 seconds to each of the
    // ten failures (about 4.5 minutes on a second back-to-back run), so leave room for both.
    test.setTimeout(600_000);
    const visitor = await (await browser.newContext()).newPage();

    // Three failures are free; after six, each attempt has to wait.
    for (let failure = 1; failure <= 6; failure += 1) await failOneSignIn(owner.request, member.email);
    await signInThroughPage(visitor, member.email, member.password);
    await expect(visitor.getByRole("alert")).toHaveText(/^Too many failed sign-in attempts\. Wait \d+ seconds?, then try again\.$/);
    await expect(visitor.getByRole("heading", { name: "Sign in" })).toBeVisible();

    // The tenth failure locks the account: the right password is refused without being checked.
    for (let failure = 7; failure <= 10; failure += 1) await failOneSignIn(owner.request, member.email);
    const refused = await directSignIn(owner.request, member.email, member.password);
    expect(refused.status()).toBe(429);
    expect(await refused.json()).toMatchObject({ locked: true });
    await signInThroughPage(visitor, member.email, member.password);
    await expect(visitor.getByRole("alert")).toHaveText(
      "Too many failed sign-in attempts. Sign-in is locked for 15 minutes. Try again after that.",
    );
    await expect(visitor.getByRole("heading", { name: "Sign in" })).toBeVisible();

    // The Owner's existing session still works, and their Audit names the lockout.
    await openAudit(owner);
    const lockout = auditRows(owner, "member.locked_out");
    await expect(lockout).toHaveCount(1);
    await expect(lockout).toContainText("System");
    await expect(lockout).toContainText('"scope":"account"');
    await expect(lockout).toContainText('"failures":10');
    await visitor.context().close();
  });

  test("a sign-in with an unregistered email fails exactly like a wrong password, and a reset request for it says the same as for a registered one", async ({
    page,
  }) => {
    // Each checkedSignIn may wait out the host IP's earlier failures (up to 45 s each).
    test.setTimeout(150_000);
    const registered = newMember();
    const unregistered = newMember();
    await signUp(page.request, registered);
    await page.context().clearCookies();

    // The page says the same for an email nobody registered as auth.spec sees for a wrong password.
    await signInThroughPage(page, unregistered.email, unregistered.password);
    await expect(page.getByRole("alert")).toHaveText(INCORRECT);

    // The API's answers are identical too, so nothing tells the two apart.
    const wrongPassword = await checkedSignIn(page.request, registered.email, "not the password at all");
    const unknownEmail = await checkedSignIn(page.request, unregistered.email, "not the password at all");
    expect(wrongPassword.status()).toBe(401);
    expect(unknownEmail.status()).toBe(wrongPassword.status());
    expect(await unknownEmail.json()).toEqual(await wrongPassword.json());

    // Asking for a reset link: the same neutral answer for both, but only a registered email gets one.
    for (const email of [unregistered.email, registered.email]) {
      await page.goto("/forgot-password");
      await page.getByLabel("Email").fill(email);
      await page.getByRole("button", { name: "Send reset link" }).click();
      await expect(page.getByRole("status")).toHaveText(RESET_SENT);
    }
    const unknownReset = await page.request.post(`${API_URL}/api/auth/password-reset`, { data: { email: unregistered.email } });
    const knownReset = await page.request.post(`${API_URL}/api/auth/password-reset`, { data: { email: registered.email } });
    expect(unknownReset.status()).toBe(202);
    expect(await unknownReset.json()).toEqual(await knownReset.json());
    await latestEmailTo(page.request, registered.email);
    expect(await emailCount(page.request, unregistered.email)).toBe(0);
  });
});

test.describe("Password reset links", () => {
  test("a reset link that has expired is refused and the old password still signs in", async ({ page }) => {
    const member = newMember();
    await signUp(page.request, member);
    await page.context().clearCookies();
    const resetLink = await requestReset(page, member.email);

    await expireLink("password_reset_tokens", linkToken(resetLink));

    await page.goto(resetLink);
    await page.getByLabel("New password", { exact: true }).fill(NEW_PASSWORD);
    await page.getByRole("button", { name: "Set new password" }).click();
    await expect(page.getByRole("alert")).toContainText(RESET_EXPIRED);
    await expect(page.getByRole("link", { name: "Request a new link" })).toBeVisible();
    await signInThroughPage(page, member.email, member.password);
    await expect(page.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible();
  });

  test("resetting the password from the emailed link signs the Member out of their other sessions", async ({
    signedInPage: otherDevice,
    member,
    browser,
  }) => {
    await otherDevice.goto("/");
    await expect(otherDevice.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible();

    const resetter = await (await browser.newContext()).newPage();
    const resetLink = await requestReset(resetter, member.email);
    await resetter.goto(resetLink);
    await resetter.getByLabel("New password", { exact: true }).fill(NEW_PASSWORD);
    await resetter.getByRole("button", { name: "Set new password" }).click();
    await expect(resetter.getByRole("status")).toHaveText(/Your password has been reset and you've been signed out everywhere\./);

    // The browser that was signed in before the reset is signed out.
    expect((await otherDevice.request.get("/api/auth/me")).status()).toBe(401);
    await otherDevice.reload();
    await expect(otherDevice.getByRole("heading", { name: "Sign in" })).toBeVisible();

    // Only the new password signs in now; the reset is audited.
    await signInAs(otherDevice, { email: member.email, password: NEW_PASSWORD });
    await openAudit(otherDevice);
    await expect(auditRows(otherDevice, "member.password_reset")).toHaveCount(1);
    await expect(auditRows(otherDevice, "member.password_reset")).toContainText(member.name);
    await resetter.context().close();
  });
});

test.describe("Invite expiry", () => {
  test("an invite past its expiry shows as Expired to the Owner and its link no longer works", async ({ signedInPage: owner, browser }) => {
    const person = newMember({ name: "Late Invitee" });
    const invited = await owner.request.post(`/api/organisations/${await organisationId(owner.request)}/invites`, {
      data: { email: person.email, role: "editor", send_email: false },
    });
    expect(invited.status()).toBe(201);
    const link = ((await invited.json()) as { link: string }).link;

    await expireLink("invites", linkToken(link));

    await owner.goto("/");
    await openSection(owner, "Organisation sections", "Settings");
    await openSection(owner, "Organisation settings", "Members");
    const pending = owner.getByRole("table", { name: "Pending invites" }).getByRole("row").filter({ hasText: person.email });
    await expect(pending.getByRole("cell", { name: "Expired", exact: true })).toBeVisible();

    const invitee = await (await browser.newContext()).newPage();
    const url = new URL(link);
    await invitee.goto(url.pathname + url.search);
    await expect(invitee.getByRole("alert")).toContainText("This invite link is invalid or has expired.");
    const joined = await invitee.request.post("/api/invites/sign-up", {
      data: { token: linkToken(link), name: person.name, password: person.password },
    });
    expect(joined.ok()).toBe(false);
    await invitee.context().close();
  });
});

test.describe("Security Audit Events", () => {
  test("role changes carry before and after values, and MFA enrolment and password changes are audited with who and when", async ({
    signedInPage: owner,
    member,
    browser,
  }) => {
    const editor = newMember({ name: "Audited Editor" });
    const editorPage = await addEditor(owner, browser, editor);

    // A role change, made in the Members tab.
    await owner.goto("/");
    await openSection(owner, "Organisation sections", "Settings");
    await openSection(owner, "Organisation settings", "Members");
    await owner.getByLabel(`Role for ${editor.name}`).selectOption("Owner");
    await expect(owner.getByText(`${editor.name} is now an Owner.`)).toBeVisible();

    // The Editor turns on MFA and changes their password.
    const enrolment = await editorPage.request.post("/api/auth/mfa/enrolment");
    expect(enrolment.ok()).toBe(true);
    const { secret } = (await enrolment.json()) as { secret: string };
    const confirmed = await editorPage.request.post("/api/auth/mfa/enrolment/confirm", { data: { code: totpCode(secret, totpStep()) } });
    expect(confirmed.ok()).toBe(true);
    const changed = await editorPage.request.post("/api/auth/me/password", {
      data: { current_password: editor.password, new_password: NEW_PASSWORD },
    });
    expect(changed.status()).toBe(204);

    const today = new Date().toISOString().slice(0, 10);
    await openAudit(owner);
    const roleChange = auditRows(owner, "member.role_changed");
    await expect(roleChange).toHaveCount(1);
    await expect(roleChange).toContainText(member.name);
    expect(await values(roleChange, "before")).toEqual({ email: editor.email, role: "editor" });
    expect(await values(roleChange, "after")).toEqual({ email: editor.email, role: "owner" });

    const enrolled = auditRows(owner, "mfa.enrolled");
    await expect(enrolled).toHaveCount(1);
    await expect(enrolled).toContainText(editor.name);
    await expect(enrolled).toContainText(today);
    expect(await values(enrolled, "before")).toEqual({ mfa_enabled: false });
    expect(await values(enrolled, "after")).toEqual({ mfa_enabled: true });

    const passwordChanged = auditRows(owner, "member.password_changed");
    await expect(passwordChanged).toHaveCount(1);
    await expect(passwordChanged).toContainText(editor.name);
    await expect(passwordChanged).toContainText(today);
    // Neither password appears in the Audit.
    const audit = await (await owner.request.get(`/api/organisations/${await organisationId(owner.request)}/audit-events?size=100`)).text();
    expect(audit).not.toContain(editor.password);
    expect(audit).not.toContain(NEW_PASSWORD);
    await editorPage.context().close();
  });
});

test.describe("Provider Credentials details", () => {
  const KEY = "sk-proj-e2e-test-only-auth-security-key-c4t1";

  test("an Owner sees when each credential was last checked, and deleting one is audited without its key", async ({
    signedInPage: page,
  }) => {
    const minute = (date: Date) => `${date.toISOString().slice(0, 16).replace("T", " ")} UTC`;
    const started = new Date();
    await page.goto("/");
    await openSection(page, "Organisation sections", "Settings");
    await openSection(page, "Organisation settings", "Credentials");
    const form = page.getByRole("region", { name: "Add a credential" });
    await form.getByLabel("Provider").selectOption("OpenAI");
    await form.getByLabel("Name").fill("Checked OpenAI");
    await form.getByLabel("API key").fill(KEY);
    await form.getByRole("button", { name: "Check and save" }).click();
    await expect(page.getByText("Checked OpenAI was checked and saved.")).toBeVisible();

    const table = page.getByRole("table", { name: "Provider Credentials" });
    const header = await table.getByRole("columnheader").allTextContents();
    const lastChecked = table.getByRole("row", { name: /Checked OpenAI/ }).getByRole("cell").nth(header.indexOf("Last checked"));
    const credentials = `/api/organisations/${await organisationId(page.request)}/credentials`;
    const stored = async () =>
      ((await (await page.request.get(credentials)).json()) as { name: string; last_checked_at: string }[]).find(
        (credential) => credential.name === "Checked OpenAI",
      )?.last_checked_at ?? "";
    const firstCheck = new Date(await stored());
    expect(firstCheck.getTime()).toBeGreaterThanOrEqual(started.getTime() - 1_000);
    expect(firstCheck.getTime()).toBeLessThanOrEqual(Date.now());
    await expect(lastChecked).toHaveText(minute(firstCheck));

    // Checking again moves the time on.
    await page.getByRole("button", { name: "Check now: Checked OpenAI" }).click();
    await expect(page.getByText("Checked OpenAI passed its check.")).toBeVisible();
    await expect.poll(async () => new Date(await stored()).getTime()).toBeGreaterThan(firstCheck.getTime());
    await expect(lastChecked).toHaveText(minute(new Date(await stored())));

    await page.getByRole("button", { name: "Delete: Checked OpenAI" }).click();
    await page.getByRole("button", { name: "Yes, delete Checked OpenAI" }).click();
    await expect(page.getByText("Checked OpenAI was deleted.")).toBeVisible();

    await openSection(page, "Organisation settings", "Audit");
    const deleted = auditRows(page, "credential.deleted");
    await expect(deleted).toHaveCount(1);
    await expect(deleted).toContainText("Checked OpenAI");
    await expect(deleted).toContainText("c4t1");
    await expect(deleted).not.toContainText(KEY.slice(0, -4));
  });
});

test.describe("Seeded showcase", () => {
  test("the demo Project's Agents are scoped to the HR or the Products Tag", async ({ page }) => {
    await signInAs(page, SEED_EDITOR);
    await page.goto("/");
    await openSection(page, "Organisation sections", "Projects");
    await page.getByRole("link", { name: "Northwind Handbook" }).click();
    for (const [agent, tag, other] of [
      ["HR helper", "HR", "Products"],
      ["Guardrail demo", "HR", "Products"],
      ["Product FAQ", "Products", "HR"],
      ["Low-budget helper", "Products", "HR"],
    ] as const) {
      await openSection(page, "Project sections", "Agents");
      await page.getByRole("link", { name: agent, exact: true }).click();
      await expect(page.getByRole("heading", { level: 1, name: agent })).toBeVisible({ timeout: 15_000 });
      await openSettings(page, "Retrieval");
      const scoping = page.getByRole("group", { name: "Tag scoping" });
      await expect(scoping.getByRole("checkbox", { name: tag, exact: true })).toBeChecked();
      await expect(scoping.getByRole("checkbox", { name: other, exact: true })).not.toBeChecked();
    }
  });

  test("the demo Project Instructions have two Versions and the Product FAQ is left behind on v1", async ({ page }) => {
    await signInAs(page, SEED_EDITOR);
    await page.goto("/");
    await openSection(page, "Organisation sections", "Projects");
    await page.getByRole("link", { name: "Northwind Handbook" }).click();
    await openSection(page, "Project sections", "Instructions");

    const history = page.getByRole("list", { name: "Instructions Versions" });
    await expect(history.getByRole("listitem", { name: "v2" })).toContainText("No promises beyond policy");
    await expect(history.getByRole("listitem", { name: "v1" })).toContainText("House style");
    await expect(page.getByText(/behind the Current Version/)).toHaveText("1 Agent behind the Current Version v2", { timeout: 15_000 });
    const table = page.getByRole("table", { name: "Instructions each Agent runs with" });
    await expect(table.getByRole("row", { name: /Product FAQ/ })).toContainText("v1Instructions behind");
    await expect(table.getByRole("row", { name: /Low-budget helper/ })).toContainText("v2");
    await expect(table.getByRole("row", { name: /Low-budget helper/ })).not.toContainText("Instructions behind");
  });

  test("the demo Organisation's Theme is Northwind's olive and saffron brand set in Lora", async ({ page }) => {
    await signInAs(page, SEED_EDITOR);
    await page.goto("/");
    await openSection(page, "Organisation sections", "Settings");
    await openSection(page, "Organisation settings", "Theme");
    await expect(page.getByRole("form", { name: "Theme" })).toBeVisible();

    await expect(page.getByLabel("Primary (light)", { exact: true })).toHaveValue("#3f5f2a");
    await expect(page.getByLabel("Accent (light)", { exact: true })).toHaveValue("#9a4508");
    await expect(page.getByLabel("Surface (light)", { exact: true })).toHaveValue("#fbf8f1");
    await expect(page.getByLabel("Font")).toHaveValue("Lora");
    const preview = page.getByRole("group", { name: "Widget preview (light)" });
    await expect(preview).toHaveCSS("font-family", /Lora/);
    await expect(preview.getByRole("button", { name: /chat/ })).toHaveCSS("background-color", "rgb(63, 95, 42)");
  });

  test("one seeded Agent overrides the Organisation Theme with its own colours", async ({ page }) => {
    test.fixme(true, "10.15: the seed sets the Organisation Theme but no Agent's Theme override (backend/app/seed has no override step)");
    await signInAs(page, SEED_EDITOR);
    const organisation = `/api/organisations/${await organisationId(page.request)}`;
    const projects = (await (await page.request.get(`${organisation}/projects`)).json()) as { id: string; name: string }[];
    const project = projects.find((candidate) => candidate.name === "Northwind Handbook");
    const agents = (await (await page.request.get(`${organisation}/projects/${project?.id ?? ""}/agents`)).json()) as { id: string; name: string }[];
    const overridden: string[] = [];
    for (const agent of agents) {
      const override = await page.request.get(`${organisation}/projects/${project?.id ?? ""}/agents/${agent.id}/theme-override`);
      const { colours } = (await override.json()) as { colours: Record<string, unknown> };
      if (Object.keys(colours).length > 0) overridden.push(agent.name);
    }
    expect(overridden.length).toBeGreaterThan(0);
  });
});

test.describe("Studio Appearance", () => {
  /** The colour scheme the Studio paints with, as the browser resolves its tokens. */
  async function painted(page: Page): Promise<string> {
    return page.evaluate(() => getComputedStyle(document.documentElement).colorScheme);
  }

  test("the Studio follows the system colour scheme until the Member chooses an Appearance", async ({ signedInPage: page }) => {
    await page.emulateMedia({ colorScheme: "dark" });
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible();
    expect(await painted(page)).toBe("dark");
    await expect(page.getByRole("button", { name: "Switch to light mode" })).toBeVisible();

    await page.emulateMedia({ colorScheme: "light" });
    await expect.poll(() => painted(page)).toBe("light");
    await expect(page.getByRole("button", { name: "Switch to dark mode" })).toBeVisible();

    // Once chosen, the system preference no longer decides.
    await page.getByRole("button", { name: "Switch to dark mode" }).click();
    await expect.poll(() => painted(page)).toBe("dark");
    await page.emulateMedia({ colorScheme: "light" });
    await page.reload();
    await expect(page.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible();
    expect(await painted(page)).toBe("dark");
  });

  test("a Member chooses light or dark from the top bar, and the choice is remembered in this browser only", async ({
    signedInPage: page,
    member,
    browser,
  }) => {
    await page.emulateMedia({ colorScheme: "light" });
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible();
    const lightBackground = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    expect(await painted(page)).toBe("light");

    await page.getByRole("banner").getByRole("button", { name: "Switch to dark mode" }).click();
    await expect.poll(() => painted(page)).toBe("dark");
    expect(await page.evaluate(() => getComputedStyle(document.body).backgroundColor)).not.toBe(lightBackground);
    await expect(page.getByRole("banner").getByRole("button", { name: "Switch to light mode" })).toBeVisible();

    // Remembered across reloads and other pages in this browser.
    await page.reload();
    await expect(page.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible();
    expect(await painted(page)).toBe("dark");
    const second = await page.context().newPage();
    await second.goto("/");
    await expect(second.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible();
    expect(await painted(second)).toBe("dark");

    // Another browser signed in as the same Member starts from the system's light scheme.
    const elsewhere = await (await browser.newContext({ colorScheme: "light" })).newPage();
    await signInAs(elsewhere, member);
    await elsewhere.goto("/");
    await expect(elsewhere.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible();
    expect(await painted(elsewhere)).toBe("light");

    // Choosing light again sticks too.
    await page.getByRole("banner").getByRole("button", { name: "Switch to light mode" }).click();
    await expect.poll(() => painted(page)).toBe("light");
    await page.reload();
    await expect(page.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible();
    expect(await painted(page)).toBe("light");
    await elsewhere.context().close();
  });

  test("a page opens in the chosen dark Appearance without first showing the light one", async ({ signedInPage: page }) => {
    await page.emulateMedia({ colorScheme: "light" });
    await page.goto("/");
    await page.getByRole("banner").getByRole("button", { name: "Switch to dark mode" }).click();
    await expect.poll(() => painted(page)).toBe("dark");

    // From the first frame the Studio renders anything, record the scheme it paints with.
    await page.addInitScript(() => {
      const frames: string[] = [];
      (window as unknown as { paintedSchemes: string[] }).paintedSchemes = frames;
      const sample = () => {
        const root = document.getElementById("root");
        if (root && root.childElementCount > 0) frames.push(getComputedStyle(document.documentElement).colorScheme);
        if (frames.length < 30) requestAnimationFrame(sample);
      };
      requestAnimationFrame(sample);
      new MutationObserver((_, observer) => {
        const root = document.getElementById("root");
        if (root && root.childElementCount > 0) {
          frames.push(getComputedStyle(document.documentElement).colorScheme);
          observer.disconnect();
        }
      }).observe(document, { childList: true, subtree: true });
    });
    for (const path of ["/", "/sign-in"]) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
      await expect.poll(() => page.evaluate(() => (window as unknown as { paintedSchemes: string[] }).paintedSchemes.length)).toBeGreaterThan(5);
      const schemes = await page.evaluate(() => (window as unknown as { paintedSchemes: string[] }).paintedSchemes);
      expect(new Set(schemes)).toEqual(new Set(["dark"]));
    }
  });
});
