import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { fakeAgentsApi, hrHelper, hrTrace, oldHelper } from "../test/agents";
import { adaSession, fakeAuthApi } from "../test/auth";
import {
  erroredResult,
  failedResult,
  fakeEvaluationApi,
  leaveCase,
  parkingCase,
  passed,
  results,
  run,
} from "../test/evaluation";
import { openSection } from "../test/navigation";
import { fakeProjectsApi, hrProject } from "../test/projects";
import { renderStudio } from "../test/render";

const organisationId = adaSession.organisations[0]?.id ?? "";
const agentPage = (agentId: string, view = "/evaluation") =>
  `/organisations/${organisationId}/projects/${hrProject.id}/agents/${agentId}${view}`;

function setUp(options: Parameters<typeof fakeEvaluationApi>[0] = {}, agents = [hrHelper]) {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeAgentsApi({ agents });
  return fakeEvaluationApi(options);
}

const setRegion = () => screen.findByRole("region", { name: "Evaluation Set" }, { timeout: 5000 });
const caseRows = async () => {
  const table = await screen.findByRole("table", { name: "Evaluation Cases" }, { timeout: 5000 });
  return within(table)
    .getAllByRole("row")
    .slice(1)
    .map((row) => within(row).getAllByRole("cell").slice(0, 2).map((cell) => cell.textContent));
};

const finished = results(run("r1000000-0000-4000-8000-000000000001", "completed", 2, 2), [
  [leaveCase, passed],
  [parkingCase, failedResult],
]);

test("Evaluation is the Agent's tab between Versions and Embed & limits", async () => {
  setUp();
  renderStudio(agentPage(hrHelper.id, ""));

  await openSection("Agent views", "Evaluation");

  expect(await setRegion()).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 2, name: "Evaluation Set" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 3, name: "No Evaluation Cases yet" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Evaluate" })).toBeDisabled();
  expect(screen.getByText("No Runs yet. Evaluate to answer the set with the Draft.")).toBeInTheDocument();
});

test("an Editor writes a case with a Reference answer; one without is refused before saving", async () => {
  const user = userEvent.setup();
  const { requests } = setUp();
  renderStudio(agentPage(hrHelper.id));
  const set = await setRegion();

  await user.click(within(set).getAllByRole("button", { name: "New case" })[0] as HTMLElement);
  const editor = await screen.findByRole("dialog", { name: "New Evaluation Case" });
  await user.type(within(editor).getByLabelText("Question"), "How much leave do I get?");
  await user.click(within(editor).getByRole("button", { name: "Save case" }));

  const reference = within(editor).getByLabelText("Reference answer");
  expect(reference).toHaveAttribute("aria-invalid", "true");
  expect(reference).toHaveAccessibleDescription(/a case needs at least one expectation/);
  expect(requests).toEqual([]);

  await user.type(reference, "Everyone gets 25 days.");
  await user.click(within(editor).getByRole("button", { name: "Save case" }));

  await waitFor(() => {
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  expect(requests).toEqual([
    { route: "create", body: { question: "How much leave do I get?", reference_answer: "Everyone gets 25 days." } },
  ]);
  expect(await caseRows()).toEqual([["How much leave do I get?", "Everyone gets 25 days."]]);
  expect(screen.getByRole("button", { name: "Evaluate" })).toBeEnabled();
});

test("a case the API refuses keeps the editor open with the reason", async () => {
  const user = userEvent.setup();
  setUp({ saveStatus: 409, saveDetail: "This Agent is archived. An Owner can restore it." });
  renderStudio(agentPage(hrHelper.id));
  const set = await setRegion();

  await user.click(within(set).getAllByRole("button", { name: "New case" })[0] as HTMLElement);
  const editor = await screen.findByRole("dialog", { name: "New Evaluation Case" });
  await user.type(within(editor).getByLabelText("Question"), "Q?");
  await user.type(within(editor).getByLabelText("Reference answer"), "A.");
  await user.click(within(editor).getByRole("button", { name: "Save case" }));

  expect(await within(editor).findByRole("alert")).toHaveTextContent("This Agent is archived. An Owner can restore it.");
});

test("a refusal without a reason says to try again", async () => {
  const user = userEvent.setup();
  setUp({ saveStatus: 500 });
  renderStudio(agentPage(hrHelper.id));
  const set = await setRegion();

  await user.click(within(set).getAllByRole("button", { name: "New case" })[0] as HTMLElement);
  const editor = await screen.findByRole("dialog", { name: "New Evaluation Case" });
  await user.type(within(editor).getByLabelText("Question"), "Q?");
  await user.type(within(editor).getByLabelText("Reference answer"), "A.");
  await user.click(within(editor).getByRole("button", { name: "Save case" }));

  expect(await within(editor).findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
  await user.click(within(editor).getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("an Editor edits a case and deletes another after confirming", async () => {
  const user = userEvent.setup();
  const { requests } = setUp({ cases: [leaveCase, parkingCase] });
  renderStudio(agentPage(hrHelper.id));
  expect(await caseRows()).toEqual([
    [leaveCase.question, leaveCase.reference_answer],
    [parkingCase.question, parkingCase.reference_answer],
  ]);

  await user.click(screen.getByRole("button", { name: `More actions for ${leaveCase.question}` }));
  await user.click(screen.getByRole("menuitem", { name: "Edit" }));
  const editor = await screen.findByRole("dialog", { name: "Edit Evaluation Case" });
  expect(within(editor).getByLabelText("Question")).toHaveValue(leaveCase.question);
  const reference = within(editor).getByLabelText("Reference answer");
  await user.clear(reference);
  await user.type(reference, "Twenty-five days.");
  await user.click(within(editor).getByRole("button", { name: "Save case" }));
  await waitFor(async () => {
    expect((await caseRows())[0]).toEqual([leaveCase.question, "Twenty-five days."]);
  });

  await user.click(screen.getByRole("button", { name: `More actions for ${parkingCase.question}` }));
  await user.click(screen.getByRole("menuitem", { name: "Delete" }));
  await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: `More actions for ${parkingCase.question}` }));
  await user.click(screen.getByRole("menuitem", { name: "Delete" }));
  const confirm = await screen.findByRole("alertdialog", { name: "Delete this Evaluation Case?" });
  expect(confirm).toHaveTextContent("Past Runs keep their copy of it.");
  await user.click(within(confirm).getByRole("button", { name: "Delete case" }));

  await waitFor(async () => {
    expect(await caseRows()).toEqual([[leaveCase.question, "Twenty-five days."]]);
  });
  expect(requests.map((request) => request.route)).toEqual(["update", "delete"]);
});

test("a refused delete says why and keeps the case", async () => {
  const user = userEvent.setup();
  setUp({ cases: [leaveCase], deleteStatus: 409, deleteDetail: "This Agent is archived. An Owner can restore it." });
  renderStudio(agentPage(hrHelper.id));
  await caseRows();

  await user.click(screen.getByRole("button", { name: `More actions for ${leaveCase.question}` }));
  await user.click(screen.getByRole("menuitem", { name: "Delete" }));
  await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Delete case" }));

  expect(await within(await setRegion()).findByRole("alert")).toHaveTextContent("This Agent is archived.");
  expect(await caseRows()).toEqual([[leaveCase.question, leaveCase.reference_answer]]);
});

test("Evaluate starts a Run, the Studio polls its progress, then shows each answer judged", async () => {
  const user = userEvent.setup();
  const runId = "r2000000-0000-4000-8000-000000000002";
  const { requests } = setUp({
    cases: [leaveCase, parkingCase],
    started: [
      results(run(runId, "queued", 0, 2), []),
      results(run(runId, "running", 1, 2), []),
      results(run(runId, "completed", 2, 2), [
        [leaveCase, passed],
        [parkingCase, erroredResult],
      ]),
    ],
  });
  renderStudio(agentPage(hrHelper.id));
  await caseRows();

  await user.click(screen.getByRole("button", { name: "Evaluate" }));

  // While it runs, Evaluate waits and the progress shows.
  expect(await screen.findByRole("button", { name: "Evaluating…" })).toBeDisabled();
  expect(await screen.findByRole("meter", { name: "Answers given" }, { timeout: 5000 })).toBeInTheDocument();
  const detail = await screen.findByRole("list", { name: "Cases" }, { timeout: 8000 });
  expect(screen.queryByRole("meter")).not.toBeInTheDocument();
  expect(await screen.findByRole("button", { name: "Evaluate" })).toBeEnabled();
  expect(requests.filter((request) => request.route === "start")).toHaveLength(1);

  const [leave, parking] = within(detail).getAllByRole("listitem").filter((item) => item.parentElement === detail);
  expect(leave).toHaveTextContent(leaveCase.question);
  expect(leave).toHaveTextContent("Outcome: Pass");
  expect(leave).toHaveTextContent(passed.answer ?? "");
  expect(within(leave as HTMLElement).getByRole("list", { name: "Verdicts" })).toHaveTextContent(
    "Reference answer: Pass. The answer gives the 25 days the reference names.",
  );
  expect(parking).toHaveTextContent("Outcome: Error");
  expect(within(parking as HTMLElement).getByRole("alert")).toHaveTextContent(erroredResult.error_reason ?? "");
  expect(within(parking as HTMLElement).queryByRole("group", { name: "Trace" })).not.toBeInTheDocument();
}, 20_000);

test("Run detail shows the sides, failing Verdicts with reasons, and each answer's Trace", async () => {
  const user = userEvent.setup();
  setUp({ cases: [leaveCase, parkingCase], runs: [finished] });
  renderStudio(agentPage(hrHelper.id));

  const runs = await screen.findByRole("list", { name: "Evaluation Runs" }, { timeout: 5000 });
  expect(within(runs).getByRole("button", { name: "Run of 2026-11-12 10:00 UTC" })).toHaveAttribute("aria-current", "true");
  expect(runs).toHaveTextContent("Completed");
  expect(runs).toHaveTextContent("2 / 2 answers");
  const detail = await screen.findByRole("region", { name: "Run of 2026-11-12 10:00 UTC" });
  expect(detail).toHaveTextContent(
    "Completed · Draft revision 3 · Instructions v2 · openai gpt-4.1-mini · judged by openai gpt-4.1-mini",
  );
  const cases = within(detail).getByRole("list", { name: "Cases" });
  const parking = within(cases).getAllByRole("listitem").filter((item) => item.parentElement === cases)[1] as HTMLElement;
  expect(parking).toHaveTextContent("Outcome: Fail");
  expect(parking).toHaveTextContent("Reference answer: In the north car park.");
  expect(within(parking).getByRole("list", { name: "Verdicts" })).toHaveTextContent(
    "Reference answer: Fail. The answer doesn't name the north car park.Grounding: Fail. Nothing cited supports it.",
  );

  const trace = within(parking).getByRole("group", { name: "Trace" });
  await user.click(within(trace).getByText("Trace"));
  expect(await within(trace).findByRole("table", { name: "Retrieved Chunks" })).toBeInTheDocument();
  expect(trace).toHaveTextContent("Instructionsv2");
});

test("a Run that failed says why; a Run without Project Instructions says so", async () => {
  const failedRun = run("r3000000-0000-4000-8000-000000000003", "failed", 1, 1, {
    error_message: "Every case errored.",
    sides: run("x", "failed", 0, 0).sides.map((side) => ({ ...side, instructions_version_number: null })),
  });
  const withoutInstructions = {
    ...passed,
    trace: { ...hrTrace, instructions_source: null, instructions_version_number: null },
  };
  setUp({
    cases: [leaveCase, parkingCase],
    runs: [results(failedRun, [[leaveCase, { ...erroredResult }], [parkingCase, withoutInstructions]])],
  });
  renderStudio(agentPage(hrHelper.id));

  const detail = await screen.findByRole("region", { name: "Run of 2026-11-12 10:00 UTC" }, { timeout: 5000 });
  expect(detail).toHaveTextContent("Failed · Draft revision 3 · no Project Instructions");
  expect(within(detail).getAllByRole("alert")[0]).toHaveTextContent("Every case errored.");
  const trace = within(detail).getByRole("group", { name: "Trace" });
  await userEvent.click(within(trace).getByText("Trace"));
  expect(await within(trace).findByText("None")).toBeInTheDocument();
});

test("an older Run is chosen from the list", async () => {
  const user = userEvent.setup();
  const older = results(
    run("r4000000-0000-4000-8000-000000000004", "completed", 1, 1, { created_at: "2026-11-01T08:00:00Z" }),
    [[leaveCase, failedResult]],
  );
  setUp({ cases: [leaveCase], runs: [finished, older] });
  renderStudio(agentPage(hrHelper.id));

  await user.click(await screen.findByRole("button", { name: "Run of 2026-11-01 08:00 UTC" }, { timeout: 5000 }));

  const detail = await screen.findByRole("region", { name: "Run of 2026-11-01 08:00 UTC" });
  expect(detail).toHaveTextContent("Outcome: Fail");
});

test("a refused Evaluate says why", async () => {
  const user = userEvent.setup();
  setUp({ cases: [leaveCase], startStatus: 409, startDetail: "This Organisation has no Default Model." });
  renderStudio(agentPage(hrHelper.id));
  await caseRows();

  await user.click(screen.getByRole("button", { name: "Evaluate" }));

  expect(await within(await setRegion()).findByRole("alert")).toHaveTextContent("This Organisation has no Default Model.");
});

test("an archived Agent's set and Runs are read only", async () => {
  setUp({ cases: [leaveCase], runs: [finished] }, [oldHelper]);
  renderStudio(agentPage(oldHelper.id));

  expect(await caseRows()).toEqual([[leaveCase.question, leaveCase.reference_answer]]);
  expect(screen.getByText(/its Evaluation Set and Runs are read only/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Evaluate" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "New case" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /More actions for/ })).not.toBeInTheDocument();
  expect(await screen.findByRole("region", { name: "Run of 2026-11-12 10:00 UTC" })).toBeInTheDocument();
});

test("an archived Agent with an empty set says so, without a New case action", async () => {
  setUp({}, [oldHelper]);
  renderStudio(agentPage(oldHelper.id));

  expect(await screen.findByRole("heading", { name: "No Evaluation Cases yet" }, { timeout: 5000 })).toBeInTheDocument();
  expect(screen.getByText("This Agent's Evaluation Set is empty.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "New case" })).not.toBeInTheDocument();
});

test("a set or Run that can't be loaded says so", async () => {
  setUp({ failCases: true, failResults: true, runs: [finished] });
  renderStudio(agentPage(hrHelper.id));

  expect(await screen.findByText("The Evaluation Set could not be loaded", {}, { timeout: 5000 })).toBeInTheDocument();
  expect(await screen.findByText("The Run could not be loaded. Try again shortly.")).toBeInTheDocument();
});

test("Runs that can't be loaded say so", async () => {
  setUp({ failRuns: true, cases: [leaveCase] });
  renderStudio(agentPage(hrHelper.id));

  expect(await screen.findByText("The Runs could not be loaded. Try again shortly.", {}, { timeout: 5000 })).toBeInTheDocument();
});

test("a refused edit keeps the editor open with the reason", async () => {
  const user = userEvent.setup();
  setUp({ cases: [leaveCase], saveStatus: 409, saveDetail: "This Agent is archived. An Owner can restore it." });
  renderStudio(agentPage(hrHelper.id));
  await caseRows();

  await user.click(screen.getByRole("button", { name: `More actions for ${leaveCase.question}` }));
  await user.click(screen.getByRole("menuitem", { name: "Edit" }));
  const editor = await screen.findByRole("dialog", { name: "Edit Evaluation Case" });
  await user.click(within(editor).getByRole("button", { name: "Save case" }));

  expect(await within(editor).findByRole("alert")).toHaveTextContent("This Agent is archived.");
});
