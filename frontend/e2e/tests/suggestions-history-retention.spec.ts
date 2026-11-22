import type { Page } from "@playwright/test";

import { expect, test } from "../fixtures";
import { openAgentView } from "../fixtures/agent";
import { signInAs } from "../fixtures/auth";
import { openSection } from "../fixtures/navigation";
import {
  CITE_LINE,
  CURT_PROMPT,
  HANDBOOK,
  type SuggestionOut,
  addCase,
  askAsVisitor,
  editDraft,
  finishedRun,
  finishedSuggestion,
  json,
  openSuggestions,
  publishedAgent,
  readSuggestion,
  startSuggestion,
  suggestionList,
  suggestionOrg,
  waitForFailedVerdicts,
} from "../fixtures/suggestion-org";

// Spec 16, "History and retention" (user stories 47–51) and the demo's seeded Suggestion (60).
// The first test builds its Suggestions in a fresh Organisation (fixtures/suggestion-org.ts), as it
// applies, publishes and deletes. The second only reads the seeded demo: `make seed` gave the HR
// helper a Suggestion made from v2's failures while v2 was Live, and the Organisation keeps
// Message text for 14 days, so its oldest evidence has been purged since.
const OWNER = { email: "owner@northwind.example", password: "northwind-owner-demo" };
const DAY = /\d{4}-\d{2}-\d{2}/.source;

/** A piece of evidence's chip in the Suggestion detail's Evidence list. */
function evidenceChips(page: Page) {
  return page.getByRole("list", { name: "Evidence", exact: true }).getByRole("link");
}

test.describe("Suggestions: history and retention", () => {
  test("[US16-47][US16-48][US16-49][US16-51][US16-46] an Owner keeps finished Suggestions as a list with their state, Cost and range; evidence points at Messages without their text, a deleted case reads \"Case deleted\", and deleting one is audited", async ({
    signedInPage: page,
    browser,
    member,
    makeAxeBuilder,
  }) => {
    test.setTimeout(360_000);
    const org = await suggestionOrg(page);
    const agent = await publishedAgent(page, org, "History helper", { systemPrompt: CURT_PROMPT });
    const caseQuestion = "How many days of annual leave do I get?";
    const caseId = await addCase(page, agent, caseQuestion, 'Everyone gets "25 days of annual leave" a year.');
    // The case fails on Version 1 (its answer cites nothing), so it is evidence too.
    const run = await json<{ id: string }>(page.request, "POST", `${agent.api}/evaluation/runs`, { sides: null });
    expect((await finishedRun(page.request, agent, run.id)).status).toBe("completed");
    const firstQuestion = `Can I carry my leave over to next year? (asked ${String(Date.now())})`;
    await askAsVisitor(browser, agent.public_id, firstQuestion);
    await waitForFailedVerdicts(page, agent, 1);
    const checked = await finishedSuggestion(page.request, agent, await startSuggestion(page.request, agent));
    expect(checked.check?.state).toBe("clear");

    await test.step("[US16-49] the Suggestion's evidence points at the Message, holding none of its text, and opens it in the Conversations viewer", async () => {
      expect(checked.evidence.map((each) => each.kind).sort()).toEqual(["evaluation_case", "live_verdict"]);
      const read = JSON.stringify(checked);
      expect(read).not.toContain(firstQuestion);
      expect(read).not.toContain("25 days of annual leave");
      expect(read).not.toContain(caseQuestion);
      const reply = checked.evidence.find((each) => each.kind === "live_verdict");
      expect(reply?.message_id).toBeTruthy();
      await openSuggestions(page, agent);
      await evidenceChips(page).filter({ hasText: "Live Verdict failed" }).click();
      await expect(page).toHaveURL(new RegExp(`/conversations/${reply?.conversation_id ?? ""}#message-${reply?.message_id ?? ""}$`));
      await expect(page.getByRole("list", { name: "Messages" })).toContainText(firstQuestion, { timeout: 15_000 });
      await expect(page.getByRole("list", { name: "Messages" })).toContainText(HANDBOOK.split(". ")[0] ?? "");
    });

    await test.step("[US16-51] the evidence of an Evaluation Case deleted since reads \"Case deleted\"", async () => {
      await json(page.request, "DELETE", `${agent.api}/evaluation/cases/${caseId}`);
      const read = await readSuggestion(page.request, agent, checked.id);
      expect(read.evidence.find((each) => each.kind === "evaluation_case")?.case_deleted).toBe(true);
      await openSuggestions(page, agent);
      await expect(evidenceChips(page).filter({ hasText: "Case deleted" })).toHaveText(new RegExp(`^E\\d+ · ${DAY} · Case deleted$`), { timeout: 15_000 });
      await expect(evidenceChips(page).filter({ hasText: "Evaluation Case failed" })).toHaveCount(0);
      // The rest of the Suggestion is intact.
      await expect(page.getByRole("table", { name: "Suggested change to the system prompt" })).toContainText(CITE_LINE);
    });

    // Version 2 goes Live, so the first Suggestion is stale; a Visitor's reply to it fails too, and
    // with no Evaluation Set left the second Suggestion isn't checked. It is then applied.
    await editDraft(page.request, agent.api, (draft) => ({ ...draft, retrieval: { ...draft.retrieval, top_k: 4 } }));
    await json(page.request, "POST", `${agent.api}/versions`, { note: "Fewer Chunks" });
    await askAsVisitor(browser, agent.public_id, `Who approves my leave? (asked ${String(Date.now())})`);
    await waitForFailedVerdicts(page, agent, 1);
    const unchecked: SuggestionOut = await finishedSuggestion(page.request, agent, await startSuggestion(page.request, agent));
    expect(unchecked.check?.state).toBe("not_checked");
    const diff = await json<{ draft_revision: number }>(page.request, "GET", `${agent.api}/suggestions/${unchecked.id}/diff`);
    await json(page.request, "POST", `${agent.api}/suggestions/${unchecked.id}/apply`, { base_revision: diff.draft_revision });

    await test.step("[US16-47] the list shows each Suggestion's state (checked, not checked, stale, applied), its Cost and its range", async () => {
      await openSuggestions(page, agent);
      const items = suggestionList(page).getByRole("listitem");
      await expect(items).toHaveCount(2, { timeout: 15_000 });
      const range = new RegExp(`${DAY} to ${DAY} \\(UTC\\)`);
      const [newest, oldest] = [items.nth(0), items.nth(1)];
      await expect(newest).toContainText("From Version 2");
      await expect(newest).toContainText("Completed");
      await expect(newest).toContainText("Not checked");
      await expect(newest).toContainText(`Applied by ${member.name}, `);
      await expect(newest).toContainText(range);
      await expect(newest).toContainText(/Cost \$\d/);
      await expect(newest).not.toContainText("Stale");
      await expect(oldest).toContainText("From Version 1");
      await expect(oldest).toContainText("Check clear");
      await expect(oldest).toContainText("Stale");
      await expect(oldest).toContainText(range);
      await expect(oldest).toContainText(/Cost \$\d/);
      await expect(oldest).not.toContainText("Applied by");
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    });

    await test.step("[US16-48] an Owner deletes the stale Suggestion; the list keeps the other", async () => {
      await suggestionList(page).getByRole("listitem").nth(1).getByRole("button", { name: /^Suggestion of / }).click();
      await page.getByRole("button", { name: "Delete Suggestion" }).click();
      const confirm = page.getByRole("alertdialog", { name: "Delete this Suggestion?" });
      await expect(confirm).toContainText("The Draft and the replies it points at are kept.");
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
      await confirm.getByRole("button", { name: "Delete Suggestion" }).click();
      await expect(page.getByText("Suggestion deleted.")).toBeVisible({ timeout: 15_000 });
      await expect(suggestionList(page).getByRole("listitem")).toHaveCount(1);
      await expect(suggestionList(page).getByRole("listitem")).toContainText("From Version 2");
      expect((await page.request.get(`${agent.api}/suggestions/${checked.id}`)).status()).toBe(404);
    });

    await test.step("[US16-46] deleting is in the Audit tab", async () => {
      await page.goto("/");
      await openSection(page, "Organisation sections", "Settings");
      await openSection(page, "Organisation settings", "Audit");
      await page.getByLabel("Action").selectOption("agent.suggestion_deleted");
      const row = page.getByRole("table", { name: "Audit Events" }).getByRole("row").filter({ hasText: "agent.suggestion_deleted" });
      await expect(row).toHaveCount(1, { timeout: 15_000 });
      await expect(row).toContainText(member.name);
      await expect(row).toContainText(checked.id);
    });
  });

  test("[US16-50][US16-60] the HR helper's seeded Suggestion still reads after the Purge: its check, a Knowledge Base gap, and purged evidence shown as \"Text purged\" with the reply's date and Live Verdict", async ({
    page,
    makeAxeBuilder,
  }) => {
    await signInAs(page, OWNER);
    await page.goto("/");
    await openSection(page, "Organisation sections", "Projects");
    await page.getByRole("link", { name: "Northwind Handbook" }).click();
    await openSection(page, "Project sections", "Agents");
    await page.getByRole("link", { name: "HR helper", exact: true }).click();
    await expect(page.getByRole("heading", { level: 1, name: "HR helper" })).toBeVisible({ timeout: 15_000 });
    const agentApi = `/api${/\/organisations\/[^/]+\/projects\/[^/]+\/agents\/[^/?#]+/.exec(page.url())?.[0] ?? ""}`;
    const listed = await json<{ id: string; base_version_number: number }[]>(page.request, "GET", `${agentApi}/suggestions`);
    const seededId = listed.find((each) => each.base_version_number === 2)?.id ?? "";
    let seeded: SuggestionOut | undefined;

    await test.step("[US16-50] through the API: purged replies keep their date and Live Verdict, and the changes and explanation are intact", async () => {
      seeded = await json<SuggestionOut>(page.request, "GET", `${agentApi}/suggestions/${seededId}`);
      const purged = seeded.evidence.filter((each) => each.text_purged);
      expect(purged.length).toBeGreaterThan(0);
      for (const each of purged) {
        expect(each.live_verdict).toBe("fail");
        expect(each.occurred_at).toMatch(new RegExp(`^${DAY}T`));
        expect(each.message_id).toBeTruthy();
      }
      expect(seeded.changes.map((change) => change.suggested_value).join("\n")).toContain(CITE_LINE);
      expect(seeded.explanation).toBeTruthy();
    });

    await test.step("[US16-60][US16-50] in the Studio: the finished, checked Suggestion with its gap, and \"Text purged\" evidence", async () => {
      await openAgentView(page, "Evaluation");
      await page.getByRole("radiogroup", { name: "Evaluation view" }).getByRole("radio", { name: "Suggestions" }).click();
      const item = suggestionList(page).getByRole("listitem").filter({ hasText: "From Version 2" });
      await expect(item).toContainText("Completed", { timeout: 15_000 });
      await expect(item).toContainText("Check clear");
      await item.getByRole("button", { name: /^Suggestion of / }).click();
      await expect(page.getByRole("region", { name: "Check against the Evaluation Set" })).toContainText(/Version 2: \d+% · Suggestion: \d+%/, { timeout: 15_000 });
      await expect(page.getByRole("list", { name: "Knowledge Base gaps" }).getByRole("heading", { level: 5 }).first()).toBeVisible();
      await expect(page.getByRole("link", { name: "Open the Knowledge Base" })).toBeVisible();
      const purged = evidenceChips(page).filter({ hasText: "Text purged" });
      await expect(purged.first()).toHaveText(new RegExp(`^E\\d+ · ${DAY} · Text purged · Live Verdict failed`));
      await expect(page.getByText(new RegExp(`^${String(seeded?.evidence.length)} of ${String(seeded?.evidence_total)} pieces of evidence in the range`))).toBeVisible();
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    });
  });
});
