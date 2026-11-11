import { expect, test } from "../fixtures";
import { HOST_URL } from "../fixtures/env";

// `make seed` runs before the suite (`make e2e`): it publishes the Guardrail demo Agent, which
// answers with the naive demo model. The stack's input Guardrail is the local ONNX classifier, so
// these are its real verdicts on the attack panel's fixed payloads.
const REFUSAL = "Sorry, I can't help with that request.";
const FALLBACK = "Sorry, I don't know the answer to that.";
const NAIVE = "Naive demo model (obeys injected instructions, not AI)";

interface Expected {
  button: string;
  input: string;
  canary: string;
  acted: string;
  reply: string;
}

const EXPECTED: Expected[] = [
  { button: "Instruction override", input: "Blocked", canary: "Not reached", acted: "Acted: Input Guardrail.", reply: REFUSAL },
  { button: "Prompt extraction", input: "Blocked", canary: "Not reached", acted: "Acted: Input Guardrail.", reply: REFUSAL },
  { button: "Role-play jailbreak", input: "Blocked", canary: "Not reached", acted: "Acted: Input Guardrail.", reply: REFUSAL },
  { button: "Encoded attack (base64)", input: "Passed", canary: "Replaced the reply", acted: "Acted: Canary token.", reply: FALLBACK },
  { button: "Benign control", input: "Passed", canary: "Quiet", acted: "No Guardrail layer acted.", reply: `${NAIVE}: From northwind-staff-handbook` },
];

test.describe("Attack panel", () => {
  test("has a button per attack category and a benign control", async ({ page, makeAxeBuilder }) => {
    await page.goto(`${HOST_URL}/demo/attacks.html`);
    await expect(page.getByRole("heading", { level: 1, name: "Attack panel" })).toBeVisible();
    const attacks = page.getByRole("list", { name: "Attacks" }).getByRole("button");
    await expect(attacks).toHaveText(EXPECTED.map((e) => e.button), { timeout: 15_000 });
    await expect(page.getByRole("status")).toHaveText("Choose an attack.");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
  });

  for (const expected of EXPECTED) {
    test(`${expected.button}: shows the reply and each Guardrail layer's outcome`, async ({ page, makeAxeBuilder }) => {
      test.setTimeout(90_000);
      await page.goto(`${HOST_URL}/demo/attacks.html`);
      await page.getByRole("button", { name: expected.button, exact: true }).click({ timeout: 15_000 });

      const result = page.getByRole("region", { name: expected.button });
      await expect(result.getByText(expected.acted, { exact: true })).toBeVisible({ timeout: 45_000 });
      const layers = result.getByRole("table", { name: "Guardrail layers" });
      await expect(layers.getByRole("row", { name: /Input Guardrail/ }).getByRole("cell").first()).toHaveText(expected.input);
      await expect(layers.getByRole("row", { name: /Canary token/ }).getByRole("cell").first()).toHaveText(expected.canary);
      await expect(result.locator("#stream")).toContainText(expected.reply);
      await expect(page.getByRole("status")).toHaveText(`${expected.button}: done.`);
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    });
  }

  test("text retracted before a Search is cleared from the reply", async ({ page }) => {
    test.setTimeout(90_000);
    // The Guardrail demo Agent is Automatic, so its stream never retracts: it is given text and
    // a `retract` event first, as an Agentic Agent's model writing before a Search would send
    // (ticket 13-10).
    await page.route("**/api/demo/attacks/benign-control", async (route) => {
      const response = await route.fetch();
      const retracted = `event: token\ndata: ${JSON.stringify({ text: "Let me look that up for you first. " })}\n\nevent: retract\ndata: {}\n\n`;
      await route.fulfill({ response, body: retracted + (await response.text()) });
    });
    await page.goto(`${HOST_URL}/demo/attacks.html`);
    await page.getByRole("button", { name: "Benign control", exact: true }).click({ timeout: 15_000 });

    const result = page.getByRole("region", { name: "Benign control" });
    await expect(result.getByText("No Guardrail layer acted.", { exact: true })).toBeVisible({ timeout: 45_000 });
    await expect(result.locator("#stream")).toContainText(`${NAIVE}: From northwind-staff-handbook`);
    await expect(result.locator("#stream")).not.toContainText("look that up");
  });

  test("the canary cuts off the encoded attack's leak: the secret never reaches the page", async ({ page }) => {
    test.setTimeout(90_000);
    await page.goto(`${HOST_URL}/demo/attacks.html`);
    await page.getByRole("button", { name: "Encoded attack (base64)" }).click({ timeout: 15_000 });
    const result = page.getByRole("region", { name: "Encoded attack (base64)" });
    await expect(result.getByText(/The Canary token cut the reply off here/)).toBeVisible({ timeout: 45_000 });
    await expect(result).not.toContainText(/canary token: [0-9a-f]{6}/i);
  });
});
