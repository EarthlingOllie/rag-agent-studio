import { expect, test } from "../fixtures";
import { openAgentView } from "../fixtures/agent";
import { signInAs } from "../fixtures/auth";
import { openSection } from "../fixtures/navigation";

// `make seed` runs before the suite (`make e2e`). The stack answers and judges with the demo model:
// its judge passes a Reference answer when the answer holds the answer's quoted key phrase, and
// grounding when the answer cites a Chunk. The HR helper's Live Version (v3) quotes the staff
// handbook by name and cites it; told not to quote, the demo model gives one uncited sentence.
const EDITOR = { email: "editor@northwind.example", password: "northwind-editor-demo" };
const KEY_PHRASE = "northwind-staff-handbook.md";
const REFERENCE_ANSWER = `Quotes the "${KEY_PHRASE}" and cites it.`;
const CURT_PROMPT = "Answer staff questions in one short sentence. Don't quote the handbook.";

interface Draft {
  behaviour: Record<string, unknown>;
  [section: string]: unknown;
}

test.describe("The evaluation loop", () => {
  test("an Editor adds a seeded thumbs-down to the HR helper's set, changes the Draft, evaluates and sees the Regression in the Publish dialog", async ({
    page,
    makeAxeBuilder,
  }) => {
    test.setTimeout(360_000);
    await signInAs(page, EDITOR);
    await page.goto("/");
    await openSection(page, "Organisation sections", "Projects");
    await page.getByRole("link", { name: "Northwind Handbook" }).click();
    await openSection(page, "Project sections", "Agents");
    await page.getByRole("link", { name: "HR helper", exact: true }).click();
    await expect(page.getByRole("heading", { level: 1, name: "HR helper" })).toBeVisible({ timeout: 15_000 });
    const agentPath = /\/organisations\/[^/]+\/projects\/[^/]+\/agents\/[^/?#]+/.exec(page.url())?.[0] ?? "";
    const agentApi = `/api${agentPath}`;
    // The case this test adds, deleted when it ends.
    const added: { id?: string | undefined } = {};

    try {
      await test.step("open a seeded thumbs-down in the Conversations viewer", async () => {
        await openAgentView(page, "Conversations");
        await page.getByRole("group", { name: "Filter Conversations" }).getByLabel("Feedback").selectOption("down");
        await expect(page).toHaveURL(/feedback=down/);
        const list = page.getByRole("list", { name: "Conversations" });
        await list.getByRole("listitem").first().getByRole("link").first().click({ timeout: 15_000 });
        await expect(page.getByRole("heading", { level: 4, name: "Conversation with HR helper" })).toBeVisible({ timeout: 15_000 });
      });

      await test.step("add it to the HR helper's Evaluation Set with a Reference answer", async () => {
        const downvoted = page
          .getByRole("list", { name: "Messages" })
          .getByRole("listitem", { name: "HR helper" })
          .filter({ has: page.getByRole("group", { name: "Visitor feedback" }).filter({ hasText: "Thumbs down" }) })
          .first();
        await downvoted.getByRole("button", { name: "More actions for this reply" }).click();
        await page.getByRole("menuitem", { name: "Add to Evaluation Set" }).click();
        const editor = page.getByRole("dialog", { name: "Add to Evaluation Set" });
        await expect(editor.getByText(/No link to the Conversation is kept/)).toBeVisible();
        await expect(editor.getByLabel("Question")).not.toHaveValue("", { timeout: 15_000 });
        await editor.getByLabel("Reference answer").fill(REFERENCE_ANSWER);
        await editor.getByRole("button", { name: "Save case" }).click();
        await expect(page.getByText("Added to the Evaluation Set.")).toBeVisible({ timeout: 15_000 });
        const cases = (await (await page.request.get(`${agentApi}/evaluation/cases`)).json()) as { id: string; reference_answer: string | null; source: string }[];
        const found = cases.find((each) => each.reference_answer === REFERENCE_ANSWER);
        expect(found?.source).toBe("from_message");
        added.id = found?.id;
      });

      await test.step("the Evaluation view lists the new case", async () => {
        await openAgentView(page, "Evaluation");
        const set = page.getByRole("table", { name: "Evaluation Cases" });
        await expect(set.getByRole("row").filter({ hasText: REFERENCE_ANSWER })).toHaveCount(1, { timeout: 15_000 });
        expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
      });

      await test.step("change the Draft: one short sentence, without quoting the handbook", async () => {
        const agent = (await (await page.request.get(agentApi)).json()) as { draft: Draft };
        const draft = { ...agent.draft, behaviour: { ...agent.draft.behaviour, system_prompt: CURT_PROMPT } };
        expect((await page.request.put(`${agentApi}/draft`, { data: draft })).ok()).toBe(true);
        await page.reload();
        await expect(page.getByTitle("The Draft has changes that aren't published yet.")).toBeVisible({ timeout: 15_000 });
      });

      await test.step("Evaluate in the Publish dialog and see the Regression", async () => {
        await page.getByRole("banner").getByRole("button", { name: "Publish" }).click();
        const publish = page.getByRole("form", { name: "Publish" });
        const evaluation = publish.getByRole("region", { name: "Evaluation" });
        // The Editor's seeded Run of the Draft against v3 describes an earlier Draft revision.
        await expect(evaluation.getByText(/changed since/)).toBeVisible({ timeout: 15_000 });
        await evaluation.getByRole("button", { name: "Evaluate" }).click();
        const regressions = evaluation.getByRole("list", { name: "Regressions" });
        await expect(regressions.getByRole("listitem").filter({ hasText: `lacks “${KEY_PHRASE.toLowerCase()}”` })).toHaveCount(1, {
          timeout: 300_000,
        });
        await expect(evaluation.getByText(/You can still Publish\./)).toBeVisible();
        await expect(publish.getByRole("button", { name: "Publish" })).toBeEnabled();
        expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
        await page.getByRole("dialog").getByRole("button", { name: "Close" }).click();
      });
    } finally {
      // Leave the seeded HR helper as the other demo tests expect it.
      await page.request.post(`${agentApi}/draft/discard`);
      if (added.id !== undefined) await page.request.delete(`${agentApi}/evaluation/cases/${added.id}`);
    }
  });
});
