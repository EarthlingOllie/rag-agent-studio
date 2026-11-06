import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi } from "../test/auth";
import { fakeBulkApi, NEVER_PUBLISHED, NOTHING_TO_REVERT, rolloutAgent } from "../test/bulk";
import { fakeProjectsApi, hrProject, instructionsVersion, oldProject, PROJECT_ARCHIVED } from "../test/projects";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const instructionsTab = (projectId: string) => `/organisations/${organisationId}/projects/${projectId}/instructions`;
const ROLLOUT = "*/api/organisations/:organisationId/projects/:projectId/instructions/rollout";
const BULK_PUBLISH = "*/api/organisations/:organisationId/projects/:projectId/agents/bulk-publish";
const BULK_REVERT = "*/api/organisations/:organisationId/projects/:projectId/agents/bulk-revert";

const v1 = instructionsVersion(1, { markdown: "Be kind." });
const v2 = instructionsVersion(2, { markdown: "Be kind.\n\nNever quote salaries.", previous_version_id: v1.id });
const v3 = instructionsVersion(3, { markdown: "Be curt.", previous_version_id: v2.id });
const pinV1 = { id: v1.id, number: 1 };
const pinV2 = { id: v2.id, number: 2 };
const pinV3 = { id: v3.id, number: 3 };

// After publishing v3: Payroll is already on it (an Editor published it by hand), HR helper and
// Benefits FAQ are behind (Benefits FAQ with Draft edits), Draft only has never been published.
const hrHelper = rolloutAgent(1, "HR helper", 2, pinV2, { behind: true });
const benefits = rolloutAgent(2, "Benefits FAQ", 4, pinV1, { behind: true, has_draft_changes: true });
const payroll = rolloutAgent(3, "Payroll", 1, pinV3);
const draftOnly = rolloutAgent(4, "Draft only", null, null);
const afterV3 = { current_version: pinV3, behind: 2, agents: [hrHelper, benefits, payroll, draftOnly] };

function setUp(options: Parameters<typeof fakeProjectsApi>[0] = {}) {
  fakeAuthApi({ signedInAs: adaSession });
  return fakeProjectsApi({
    instructions: { [hrProject.id]: v2.markdown },
    versions: { [hrProject.id]: { current_version_id: v2.id, versions: [v2, v1] } },
    ...options,
  });
}

async function publishInstructions(markdown: string) {
  await userEvent.click(await screen.findByRole("button", { name: "Markdown" }, { timeout: 5000 }));
  const source = screen.getByRole("textbox", { name: "Project Instructions (Markdown)" });
  await userEvent.clear(source);
  await userEvent.type(source, markdown);
  const form = screen.getByRole("form", { name: "Publish Instructions" });
  await userEvent.type(within(form).getByRole("textbox", { name: "Note" }), "Curt");
  await userEvent.click(within(form).getByRole("button", { name: "Publish Instructions" }));
}

test("publishing Instructions opens the rollout dialog with the Agents that can take it pre-selected", async () => {
  setUp();
  const { requests } = fakeBulkApi({ rollout: afterV3 });
  renderStudio(instructionsTab(hrProject.id));

  await publishInstructions("Be curt.");

  const dialog = await screen.findByRole("dialog", { name: "Roll out Instructions v3" });
  expect(dialog).toHaveTextContent("built from its Live configuration with Instructions v3");
  expect(dialog).toHaveTextContent("Unpublished Draft changes are not included.");
  expect(within(dialog).getByRole("checkbox", { name: "HR helper" })).toBeChecked();
  expect(within(dialog).getByRole("checkbox", { name: "Benefits FAQ" })).toBeChecked();
  // Already on v3, or never published: not offered.
  expect(within(dialog).getByRole("checkbox", { name: "Payroll" })).toBeDisabled();
  expect(within(dialog).getByRole("checkbox", { name: "Payroll" })).not.toBeChecked();
  expect(within(dialog).getByRole("checkbox", { name: "Draft only" })).toBeDisabled();
  const rows = within(within(dialog).getByRole("list", { name: "Agents" })).getAllByRole("listitem");
  expect(rows.map((row) => row.textContent)).toEqual([
    "HR helperLive v2, Instructions v2",
    "Benefits FAQLive v4, Instructions v1Unpublished Draft changes (not included)",
    "PayrollLive v1, Instructions v3Already on v3.",
    "Draft onlyNot liveNever published: not included. Publish it from its page first.",
  ]);

  await userEvent.click(within(dialog).getByRole("button", { name: "Publish to 2 Agents" }));

  expect(requests).toEqual([
    { route: "bulk-publish", body: { agent_ids: [hrHelper.id, benefits.id], instructions_version_id: v3.id } },
  ]);
  const results = await within(dialog).findByRole("list", { name: "Results" });
  expect(within(results).getAllByRole("listitem").map((row) => row.textContent)).toEqual([
    "HR helper — Done: Published v3 with Instructions v3. It is now Live.",
    "Benefits FAQ — Done: Published v5 with Instructions v3. It is now Live.",
  ]);
  await userEvent.click(within(dialog).getByRole("button", { name: "Done" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("the Editor can deselect Agents to keep them on older Instructions", async () => {
  setUp();
  const { requests } = fakeBulkApi({ rollout: afterV3 });
  renderStudio(instructionsTab(hrProject.id));
  await publishInstructions("Be curt.");
  const dialog = await screen.findByRole("dialog", { name: "Roll out Instructions v3" });

  await userEvent.click(within(dialog).getByRole("checkbox", { name: "Benefits FAQ" }));
  await userEvent.click(within(dialog).getByRole("checkbox", { name: "HR helper" }));
  expect(within(dialog).getByRole("button", { name: "Publish to 0 Agents" })).toBeDisabled();
  await userEvent.click(within(dialog).getByRole("checkbox", { name: "HR helper" }));
  await userEvent.click(within(dialog).getByRole("button", { name: "Publish to 1 Agent" }));

  expect(requests).toEqual([{ route: "bulk-publish", body: { agent_ids: [hrHelper.id], instructions_version_id: v3.id } }]);
});

test("the results say which Agents were skipped or failed, and why", async () => {
  setUp();
  fakeBulkApi({
    rollout: afterV3,
    respond: () =>
      HttpResponse.json({
        bulk_operation_id: "b0000000-0000-4000-8000-000000000009",
        results: [
          { agent_id: hrHelper.id, name: "HR helper", status: "skipped", reason: NEVER_PUBLISHED, live_version: null, instructions_version: null },
          { agent_id: benefits.id, name: null, status: "failed", reason: "Not found.", live_version: null, instructions_version: null },
        ],
      }),
  });
  renderStudio(instructionsTab(hrProject.id));
  await publishInstructions("Be curt.");
  const dialog = await screen.findByRole("dialog", { name: "Roll out Instructions v3" });

  await userEvent.click(within(dialog).getByRole("button", { name: "Publish to 2 Agents" }));

  const results = await within(dialog).findByRole("list", { name: "Results" });
  expect(within(results).getAllByRole("listitem").map((row) => row.textContent)).toEqual([
    `HR helper — Skipped: ${NEVER_PUBLISHED}`,
    "Unknown Agent — Failed: Not found.",
  ]);
});

test("a bulk publish refused as a whole says why and shows its progress", async () => {
  setUp();
  fakeBulkApi({ rollout: afterV3 });
  server.use(
    http.post(BULK_PUBLISH, async () => {
      await delay(100);
      return HttpResponse.json({ detail: PROJECT_ARCHIVED }, { status: 409 });
    }),
  );
  renderStudio(instructionsTab(hrProject.id));
  await publishInstructions("Be curt.");
  const dialog = await screen.findByRole("dialog", { name: "Roll out Instructions v3" });

  await userEvent.click(within(dialog).getByRole("button", { name: "Publish to 2 Agents" }));

  expect(await within(dialog).findByRole("button", { name: "Publishing…" })).toBeDisabled();
  expect(await within(dialog).findByRole("alert")).toHaveTextContent(PROJECT_ARCHIVED);
  server.use(http.post(BULK_PUBLISH, () => HttpResponse.json({}, { status: 500 })));
  await userEvent.click(within(dialog).getByRole("button", { name: "Publish to 2 Agents" }));
  expect(await within(dialog).findByText("Something went wrong, so nothing was changed. Try again.")).toBeInTheDocument();
  await userEvent.click(within(dialog).getByRole("button", { name: "Not now" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("the Instructions page shows how many Agents are behind and which Version each one pins", async () => {
  setUp();
  const v2Live = { current_version: pinV2, behind: 1, agents: [rolloutAgent(1, "HR helper", 2, pinV2), rolloutAgent(2, "Old", 1, pinV1, { behind: true }), rolloutAgent(3, "Bare", 1, null, { behind: true }), draftOnly] };
  fakeBulkApi({ rollout: { ...v2Live, behind: 2 } });
  renderStudio(instructionsTab(hrProject.id));

  expect(await screen.findByText("2 Agents behind the Current Version (v2).")).toBeInTheDocument();
  const table = screen.getByRole("table", { name: "Instructions each Agent runs with" });
  expect(within(table).getAllByRole("row").map((row) => row.textContent)).toEqual([
    "AgentLive VersionInstructions",
    "HR helperv2v2",
    "Oldv1v1 (behind)",
    "Barev1None (behind)",
    "Draft onlyNot live",
  ]);

  // Rolling out the Current Version is one click away.
  await userEvent.click(screen.getByRole("button", { name: "Roll out v2…" }));
  const dialog = await screen.findByRole("dialog", { name: "Roll out Instructions v2" });
  expect(within(dialog).getByRole("checkbox", { name: "HR helper" })).toBeDisabled();
  expect(within(dialog).getByRole("checkbox", { name: "Old" })).toBeChecked();
});

test("one Agent behind is singular, and none behind offers no rollout", async () => {
  setUp();
  fakeBulkApi({ rollout: { current_version: pinV2, behind: 1, agents: [rolloutAgent(2, "Old", 1, pinV1, { behind: true })] } });
  const { unmount } = renderStudio(instructionsTab(hrProject.id));
  expect(await screen.findByText("1 Agent behind the Current Version (v2).")).toBeInTheDocument();
  unmount();

  fakeBulkApi({ rollout: { current_version: pinV2, behind: 0, agents: [rolloutAgent(1, "HR helper", 2, pinV2)] } });
  renderStudio(instructionsTab(hrProject.id));
  expect(await screen.findByText("0 Agents behind the Current Version (v2).")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Roll out/ })).not.toBeInTheDocument();
});

test("unpublished Instructions list each Agent without a count", async () => {
  setUp({ versions: {} });
  fakeBulkApi({ rollout: { current_version: null, behind: 0, agents: [rolloutAgent(1, "HR helper", 1, null)] } });
  renderStudio(instructionsTab(hrProject.id));

  expect(await screen.findByRole("table", { name: "Instructions each Agent runs with" })).toHaveTextContent("HR helperv1None");
  expect(screen.queryByText(/behind the Current Version/)).not.toBeInTheDocument();
});

test("an archived Project shows who is behind without offering a rollout", async () => {
  setUp();
  fakeBulkApi({ rollout: afterV3 });
  renderStudio(instructionsTab(oldProject.id));

  expect(await screen.findByText("2 Agents behind the Current Version (v3).")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Roll out/ })).not.toBeInTheDocument();
});

test("a Project without Agents says so, in the summary and the dialog", async () => {
  setUp();
  renderStudio(instructionsTab(hrProject.id));

  expect(await screen.findByText("This Project has no Agents yet.")).toBeInTheDocument();
  await publishInstructions("Be curt.");
  const dialog = await screen.findByRole("dialog", { name: "Roll out Instructions v3" });
  expect(await within(dialog).findByText("This Project has no Agents yet.")).toBeInTheDocument();
  expect(within(dialog).getByRole("button", { name: "Publish to 0 Agents" })).toBeDisabled();
});

test("Agents that can't be loaded say so, in the summary and the dialog", async () => {
  setUp();
  server.use(http.get(ROLLOUT, () => HttpResponse.json({ detail: "Not found" }, { status: 404 })));
  renderStudio(instructionsTab(hrProject.id));

  expect(await screen.findByText("The Agents' Instructions could not be loaded. Try again shortly.")).toBeInTheDocument();
  await publishInstructions("Be curt.");
  const dialog = await screen.findByRole("dialog", { name: "Roll out Instructions v3" });
  expect(await within(dialog).findByRole("alert")).toHaveTextContent("The Agents could not be loaded. Try again shortly.");
});

test("the dialog says while the Agents load", async () => {
  setUp();
  server.use(
    http.get(ROLLOUT, async () => {
      await delay(2500);
      return HttpResponse.json(afterV3);
    }),
  );
  renderStudio(instructionsTab(hrProject.id));

  await publishInstructions("Be curt.");

  const dialog = await screen.findByRole("dialog", { name: "Roll out Instructions v3" });
  expect(within(dialog).getByRole("status")).toHaveTextContent("Loading the Agents…");
  expect(await within(dialog).findByRole("checkbox", { name: "HR helper" }, { timeout: 5000 })).toBeChecked();
});

// Reverting Instructions offers a bulk revert

const candidates = [
  { id: hrHelper.id, name: "HR helper", live_version: { id: "a2e00000-0000-4000-8000-000000000103", number: 3 } },
  { id: benefits.id, name: "Benefits FAQ", live_version: { id: "a2e00000-0000-4000-8000-000000000205", number: 5 } },
];

async function revertInstructions() {
  await userEvent.click(await screen.findByRole("button", { name: "Revert to v2" }, { timeout: 5000 }));
  await userEvent.click(screen.getByRole("button", { name: "Yes, revert to v2" }));
}

test("reverting Instructions offers to bulk-revert the Agents pinned to the reverted Version", async () => {
  setUp({ versions: { [hrProject.id]: { current_version_id: v3.id, versions: [v3, v2, v1] } }, revertCandidates: candidates });
  const { requests } = fakeBulkApi({
    rollout: { current_version: pinV3, behind: 0, agents: [rolloutAgent(1, "HR helper", 3, pinV3), rolloutAgent(2, "Benefits FAQ", 5, pinV3)] },
  });
  renderStudio(instructionsTab(hrProject.id));

  await revertInstructions();

  const dialog = await screen.findByRole("dialog", { name: "Revert the Agents on Instructions v3?" });
  expect(dialog).toHaveTextContent("These Agents are Live with Instructions v3.");
  expect(within(dialog).getByRole("checkbox", { name: "HR helper (Live v3)" })).toBeChecked();
  await userEvent.click(within(dialog).getByRole("checkbox", { name: "Benefits FAQ (Live v5)" }));
  await userEvent.click(within(dialog).getByRole("checkbox", { name: "HR helper (Live v3)" }));
  expect(within(dialog).getByRole("button", { name: "Revert 0 Agents" })).toBeDisabled();
  await userEvent.click(within(dialog).getByRole("checkbox", { name: "Benefits FAQ (Live v5)" }));
  await userEvent.click(within(dialog).getByRole("checkbox", { name: "HR helper (Live v3)" }));
  await userEvent.click(within(dialog).getByRole("button", { name: "Revert 2 Agents" }));

  expect(requests).toEqual([{ route: "bulk-revert", body: { agent_ids: [hrHelper.id, benefits.id] } }]);
  const results = await within(dialog).findByRole("list", { name: "Results" });
  expect(within(results).getAllByRole("listitem").map((row) => row.textContent)).toEqual([
    "HR helper — Done: Reverted to v2 without Project Instructions. It is now Live.",
    "Benefits FAQ — Done: Reverted to v4 without Project Instructions. It is now Live.",
  ]);
  await userEvent.click(within(dialog).getByRole("button", { name: "Done" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("the bulk-revert offer can be declined, and shows its progress and refusals", async () => {
  setUp({ versions: { [hrProject.id]: { current_version_id: v3.id, versions: [v3, v2, v1] } }, revertCandidates: candidates.slice(0, 1) });
  fakeBulkApi();
  server.use(
    http.post(BULK_REVERT, async () => {
      await delay(100);
      return HttpResponse.json({ detail: NOTHING_TO_REVERT }, { status: 409 });
    }),
  );
  renderStudio(instructionsTab(hrProject.id));
  await revertInstructions();
  const dialog = await screen.findByRole("dialog", { name: "Revert the Agents on Instructions v3?" });

  await userEvent.click(within(dialog).getByRole("button", { name: "Revert 1 Agent" }));

  expect(await within(dialog).findByRole("button", { name: "Reverting…" })).toBeDisabled();
  expect(await within(dialog).findByRole("alert")).toHaveTextContent(NOTHING_TO_REVERT);
  await userEvent.click(within(dialog).getByRole("button", { name: "Not now" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("reverting Instructions no Agent is pinned to offers nothing", async () => {
  setUp({ versions: { [hrProject.id]: { current_version_id: v3.id, versions: [v3, v2, v1] } } });
  renderStudio(instructionsTab(hrProject.id));

  await revertInstructions();

  expect(await screen.findByText("Reverted to v2")).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
