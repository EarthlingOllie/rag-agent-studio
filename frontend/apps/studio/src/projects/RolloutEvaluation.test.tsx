import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { adaSession, fakeAuthApi } from "../test/auth";
import { fakeBulkApi, rolloutAgent } from "../test/bulk";
import { fakeRolloutEvaluationApi, liveSide, rolloutAgentEvaluation, run } from "../test/evaluation";
import { fakeProjectsApi, hrProject, instructionsVersion } from "../test/projects";
import { renderStudio } from "../test/render";

const organisationId = adaSession.organisations[0]?.id ?? "";
const instructionsTab = `/organisations/${organisationId}/projects/${hrProject.id}/instructions`;

const v1 = instructionsVersion(1, { markdown: "Be kind." });
const v2 = instructionsVersion(2, { markdown: "Be kind.\n\nNever quote salaries.", previous_version_id: v1.id });
const v3 = instructionsVersion(3, { markdown: "Be curt.", previous_version_id: v2.id });
const pinV2 = { id: v2.id, number: 2 };
const pinV3 = { id: v3.id, number: 3 };

// After publishing v3: HR helper and Benefits FAQ can take it, Payroll is already on it.
const hrHelper = rolloutAgent(1, "HR helper", 2, pinV2, { behind: true });
const benefits = rolloutAgent(2, "Benefits FAQ", 4, pinV2, { behind: true });
const payroll = rolloutAgent(3, "Payroll", 1, pinV3);
const afterV3 = { current_version: pinV3, behind: 2, agents: [hrHelper, benefits, payroll] };

const rolloutRun = (status: "queued" | "completed", done: number) =>
  run("ra000000-0000-4000-8000-00000000000a", status, done, 4, {
    kind: "rollout",
    sides: [liveSide, { ...liveSide, position: "second", kind: "rollout", instructions_version_number: 3 }],
  });
const regression = {
  case_id: "e1000000-0000-4000-8000-000000000001",
  question: "How much leave do I get?",
  reasons: [{ kind: "reference_answer", reason: "It gives 20 days, not 25." }],
};

const notEvaluated = {
  instructions_version_number: 3,
  agents: [
    rolloutAgentEvaluation(hrHelper.id, hrHelper.name, "not_evaluated"),
    rolloutAgentEvaluation(benefits.id, benefits.name, "not_evaluated", { has_set: false }),
    rolloutAgentEvaluation(payroll.id, payroll.name, "not_evaluated"),
  ],
};
const running = {
  ...notEvaluated,
  agents: [rolloutAgentEvaluation(hrHelper.id, hrHelper.name, "running", { run: rolloutRun("queued", 1) }), ...notEvaluated.agents.slice(1)],
};
const evaluated = {
  ...notEvaluated,
  agents: [
    rolloutAgentEvaluation(hrHelper.id, hrHelper.name, "regressions", { run: rolloutRun("completed", 4), regressions: [regression] }),
    ...notEvaluated.agents.slice(1),
  ],
};

async function openRolloutDialog() {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi({
    instructions: { [hrProject.id]: v2.markdown },
    versions: { [hrProject.id]: { current_version_id: v2.id, versions: [v2, v1] } },
  });
  const bulk = fakeBulkApi({ rollout: afterV3 });
  renderStudio(instructionsTab);
  await userEvent.click(await screen.findByRole("button", { name: "Markdown" }, { timeout: 5000 }));
  const source = screen.getByRole("textbox", { name: "Project Instructions (Markdown)" });
  await userEvent.clear(source);
  await userEvent.type(source, "Be curt.");
  const form = screen.getByRole("form", { name: "Publish Instructions" });
  await userEvent.type(within(form).getByRole("textbox", { name: "Note" }), "Curt");
  await userEvent.click(within(form).getByRole("button", { name: "Publish Instructions" }));
  const dialog = await screen.findByRole("dialog", { name: "Roll out Instructions v3" });
  return { dialog, bulk };
}

const rows = (dialog: HTMLElement) => within(within(dialog).getByRole("list", { name: "Agents" })).getAllByRole("listitem");

test("Evaluate rollout evaluates the selected Agents and shows each one's Regressions, never deselecting or blocking it", async () => {
  const { requests } = fakeRolloutEvaluationApi({ reads: [notEvaluated, running, running, evaluated] });
  const { dialog, bulk } = await openRolloutDialog();

  // Each Agent that can take the Instructions has an evaluation column; Payroll is already on v3.
  await within(dialog).findAllByText("Not evaluated");
  expect(rows(dialog).map((row) => row.textContent)).toEqual([
    "HR helperLive v2, Instructions v2Not evaluated",
    "Benefits FAQLive v4, Instructions v2Not evaluated: no Evaluation Set",
    "PayrollLive v1, Instructions v3Already on v3.",
  ]);
  expect(dialog).toHaveTextContent(
    "Evaluate rollout runs each selected Agent's Evaluation Set with its Live configuration and Instructions v3, against its Live Version as it is.",
  );

  await userEvent.click(within(dialog).getByRole("button", { name: "Evaluate rollout" }));

  expect(requests).toEqual([{ route: "start-rollout", body: { agent_ids: [hrHelper.id, benefits.id] } }]);
  // While it runs, its progress shows and Evaluate rollout waits.
  expect(await within(dialog).findByText("Evaluating, 1 of 4 answers")).toBeInTheDocument();
  expect(within(dialog).getByRole("button", { name: "Evaluating…" })).toBeDisabled();
  // Then each Regression, with why it failed.
  const hr = await within(dialog).findByText("1 Regression", {}, { timeout: 5000 });
  expect(hr.closest("li")).toHaveTextContent("How much leave do I get?Reference answer: It gives 20 days, not 25.");
  expect(within(dialog).getByRole("status")).toHaveTextContent(
    "HR helper has Regressions with Instructions v3: cases that pass on the Live Version fail with the new Instructions. You can still publish.",
  );
  // Never deselected, never blocked.
  expect(within(dialog).getByRole("checkbox", { name: "HR helper" })).toBeChecked();
  await userEvent.click(within(dialog).getByRole("button", { name: "Publish to 2 Agents" }));
  expect(bulk.requests).toEqual([{ route: "bulk-publish", body: { agent_ids: [hrHelper.id, benefits.id], instructions_version_id: v3.id } }]);
});

test("Agents with Regressions are warned about only while selected; a clear Agent says so", async () => {
  const both = {
    ...notEvaluated,
    agents: [
      rolloutAgentEvaluation(hrHelper.id, hrHelper.name, "regressions", { run: rolloutRun("completed", 4), regressions: [regression, { ...regression, case_id: null, question: "Q?" }] }),
      rolloutAgentEvaluation(benefits.id, benefits.name, "regressions", { run: rolloutRun("completed", 4), regressions: [regression] }),
    ],
  };
  fakeRolloutEvaluationApi({ reads: [both] });
  const { dialog } = await openRolloutDialog();

  expect(await within(dialog).findByText("2 Regressions")).toBeInTheDocument();
  expect(within(dialog).getByRole("status")).toHaveTextContent("HR helper, Benefits FAQ have Regressions with Instructions v3");
  await userEvent.click(within(dialog).getByRole("checkbox", { name: "Benefits FAQ" }));
  expect(within(dialog).getByRole("status")).toHaveTextContent("HR helper has Regressions with Instructions v3");
  await userEvent.click(within(dialog).getByRole("checkbox", { name: "HR helper" }));
  expect(within(dialog).queryByRole("status")).not.toBeInTheDocument();
  // Nothing selected: nothing to evaluate.
  expect(within(dialog).getByRole("button", { name: "Evaluate rollout" })).toBeDisabled();
});

test("a clear Rollout evaluation says so, and a refused one says why", async () => {
  const clear = {
    ...notEvaluated,
    agents: [rolloutAgentEvaluation(hrHelper.id, hrHelper.name, "clear", { run: rolloutRun("completed", 4) })],
  };
  fakeRolloutEvaluationApi({
    reads: [clear],
    startStatus: 409,
    startDetail: "HR helper already has an Evaluation Run in progress. Wait for it to finish, or cancel it, then evaluate the rollout again.",
  });
  const { dialog } = await openRolloutDialog();

  expect(await within(dialog).findByText("No Regressions")).toBeInTheDocument();
  await userEvent.click(within(dialog).getByRole("button", { name: "Evaluate rollout" }));

  expect(await within(dialog).findByText(/HR helper already has an Evaluation Run in progress/)).toBeInTheDocument();
});

test("a Rollout evaluation that can't be loaded says so, and the rollout is still offered", async () => {
  fakeRolloutEvaluationApi({ reads: { status: 500 } });
  const { dialog } = await openRolloutDialog();

  expect(await within(dialog).findByText("The Rollout evaluation could not be loaded.", {}, { timeout: 5000 })).toBeInTheDocument();
  expect(within(dialog).getByRole("button", { name: "Publish to 2 Agents" })).toBeEnabled();
});
