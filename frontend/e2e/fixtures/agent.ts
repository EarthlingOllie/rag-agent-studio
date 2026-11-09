import type { Page } from "@playwright/test";

import { openSection } from "./navigation";

/** Opens an Agent view (Playground, Versions, Embed & limits, Conversations) from the breadcrumb. */
export async function openAgentView(page: Page, view: "Playground" | "Versions" | "Embed & limits" | "Conversations") {
  await openSection(page, "Agent views", view);
}

/** Chooses an item in the Agent's ⋯ menu (Discard Draft, Archive, Delete permanently). */
export async function agentAction(page: Page, item: string) {
  await page.getByRole("button", { name: "More Agent actions" }).click();
  await page.getByRole("menu", { name: "Agent actions" }).getByRole("menuitem", { name: item }).click();
}

/** Opens a section of the Draft's configuration (Behaviour, Retrieval, Experience, Guardrails) if it is folded. */
export async function openSettings(page: Page, section: "Behaviour" | "Retrieval" | "Experience" | "Guardrails") {
  const details = page.getByRole("complementary", { name: "Configuration" }).locator("details").filter({
    has: page.locator(`fieldset[aria-label="${section}"]`),
  });
  if (!(await details.evaluate((element) => (element as HTMLDetailsElement).open))) {
    await details.locator("summary").click();
  }
}

/** Publishes the Agent's saved Draft from the top bar's Publish dialog, then closes the dialog. */
export async function publishAgent(page: Page, note: string, instructions?: string) {
  await page.getByRole("banner").getByRole("button", { name: "Publish" }).click();
  const publish = page.getByRole("form", { name: "Publish" });
  await publish.getByLabel("Note").fill(note);
  if (instructions !== undefined) await publish.getByLabel("Project Instructions").selectOption({ label: instructions });
  await publish.getByRole("button", { name: "Publish" }).click();
  await publish.getByRole("status").getByText(/It is now Live\./).waitFor({ timeout: 15_000 });
  await page.getByRole("dialog").getByRole("button", { name: "Close" }).click();
}

/** The Agent's Live Version chip in its header ("Version 3"). */
export function liveVersion(page: Page, number: number) {
  return page.getByLabel(`Version ${String(number)}`, { exact: true }).first();
}

/** In the Embed & limits view: adds each origin to the Allowed Origins, then saves them. */
export async function saveAllowedOrigins(page: Page, origins: string[]) {
  const card = page.getByRole("region", { name: "Allowed Origins" });
  const input = card.getByRole("textbox", { name: "Add an Allowed Origin" });
  for (const origin of origins) {
    await input.fill(origin);
    await input.press("Enter");
  }
  await card.getByRole("button", { name: "Save Allowed Origins" }).click();
  await card.getByText("Saved. Pages on these sites can show the Agent now.").waitFor({ timeout: 15_000 });
}
