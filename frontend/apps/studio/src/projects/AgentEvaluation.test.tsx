import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { agentVersion, fakeAgentsApi, hrHelper, hrTrace, oldHelper } from "../test/agents";
import { adaSession, fakeAuthApi } from "../test/auth";
import {
  caseSide,
  draftSide,
  erroredResult,
  failedResult,
  fakeEvaluationApi,
  leaveCase,
  liveSide,
  parkingCase,
  passed,
  repeat,
  results,
  run,
} from "../test/evaluation";
import { openSection } from "../test/navigation";
import { fakeProjectsApi, hrProject, instructionsVersion } from "../test/projects";
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
  // Never Published: the Draft runs alone, with the Current Instructions Version.
  const dialog = await screen.findByRole("dialog", { name: "Evaluate" });
  expect(within(dialog).getByLabelText("First side")).toHaveDisplayValue("Draft");
  expect(within(dialog).getByLabelText("Second side")).toHaveDisplayValue("None: the first side runs alone");
  await user.click(within(dialog).getByRole("button", { name: "Start Run" }));

  // While it runs, Evaluate waits and the progress shows.
  expect(await screen.findByRole("button", { name: "Evaluating…" })).toBeDisabled();
  expect(await screen.findByRole("meter", { name: "Answers given" }, { timeout: 5000 })).toBeInTheDocument();
  const detail = await screen.findByRole("list", { name: "Cases" }, { timeout: 8000 });
  expect(screen.queryByRole("meter")).not.toBeInTheDocument();
  expect(await screen.findByRole("button", { name: "Evaluate" })).toBeEnabled();
  expect(requests.filter((request) => request.route === "start")).toEqual([
    { route: "start", body: { sides: [{ kind: "draft" }], instructions_draft: false, instructions_version_id: null } },
  ]);

  const [leave, parking] = within(detail).getAllByRole("listitem").filter((item) => item.parentElement === detail);
  expect(leave).toHaveTextContent(leaveCase.question);
  expect(leave).toHaveTextContent("Repeat 1: Pass");
  expect(leave).toHaveTextContent(passed.answer ?? "");
  expect(within(leave as HTMLElement).getByRole("list", { name: "Verdicts" })).toHaveTextContent(
    "Reference answer: Pass. The answer gives the 25 days the reference names.",
  );
  expect(parking).toHaveTextContent("Repeat 1: Error");
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
  expect(parking).toHaveTextContent("Repeat 1: Fail");
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
    sides: run("x", "failed", 0, 0).sides.map((side) => ({
      ...side,
      instructions_version_number: null,
      cases_passed: 0,
      cases_failed: 0,
      cases_errored: 2,
      score: null,
    })),
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
  expect(detail).toHaveTextContent("Evaluation score: none, every case was an Error");
  expect(detail).toHaveTextContent("0 passed, 0 failed, 2 Errors left out of the score");
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
  expect(detail).toHaveTextContent("Repeat 1: Fail");
});

test("a refused Evaluate says why", async () => {
  const user = userEvent.setup();
  setUp({ cases: [leaveCase], startStatus: 409, startDetail: "This Organisation has no Default Model." });
  renderStudio(agentPage(hrHelper.id));
  await caseRows();

  await user.click(screen.getByRole("button", { name: "Evaluate" }));
  const dialog = await screen.findByRole("dialog", { name: "Evaluate" });
  await user.click(within(dialog).getByRole("button", { name: "Start Run" }));

  expect(await within(dialog).findByRole("alert")).toHaveTextContent("This Organisation has no Default Model.");
  await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
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

test("the set shows each case's latest result: pass, fail, Unsteady or Error", async () => {
  const latest = (outcome: "pass" | "fail" | "error", passed: number, answered: number, unsteady = false) => ({
    run_id: "r1000000-0000-4000-8000-000000000001",
    outcome,
    passed,
    answered,
    repeats: 3,
    unsteady,
  });
  setUp({
    cases: [
      { ...leaveCase, latest_result: latest("pass", 3, 3) },
      { ...parkingCase, latest_result: latest("pass", 2, 3, true) },
      { ...parkingCase, id: "e1000000-0000-4000-8000-000000000003", question: "Failing?", latest_result: latest("fail", 0, 3) },
      { ...parkingCase, id: "e1000000-0000-4000-8000-000000000004", question: "Errored?", latest_result: latest("error", 0, 0) },
      { ...parkingCase, id: "e1000000-0000-4000-8000-000000000005", question: "New?" },
    ],
  });
  renderStudio(agentPage(hrHelper.id));

  const table = await screen.findByRole("table", { name: "Evaluation Cases" }, { timeout: 5000 });
  const latestResults = within(table)
    .getAllByRole("row")
    .slice(1)
    .map((row) => within(row).getAllByRole("cell")[2]?.textContent);
  expect(within(table).getByRole("columnheader", { name: "Latest result" })).toBeInTheDocument();
  expect(latestResults).toEqual(["Pass3/3", "PassUnsteady2/3", "Fail0/3", "Error", "Not run yet"]);
});

test("Run detail combines each case's repeats: the majority with its count, Unsteady, Error, and the score", async () => {
  const runId = "r5000000-0000-4000-8000-000000000005";
  const combined = results(
    run(runId, "completed", 9, 9, {
      repeats: 3,
      sides: run("x", "completed", 0, 0).sides.map((side) => ({ ...side, cases_passed: 1, cases_failed: 1, cases_errored: 1, score: 0.5 })),
    }),
    [
      [leaveCase, [repeat(passed, 1), repeat(failedResult, 2), repeat(passed, 3)], caseSide("pass", 2, 3, 3), true],
      [parkingCase, [repeat(failedResult, 1), repeat(failedResult, 2), repeat(erroredResult, 3)], caseSide("fail", 0, 2, 3)],
      [
        { ...parkingCase, question: "Errored?" },
        [repeat(erroredResult, 1), repeat(erroredResult, 2), repeat(erroredResult, 3)],
        caseSide("error", 0, 0, 3),
      ],
    ],
  );
  setUp({ cases: [leaveCase, parkingCase], runs: [combined] });
  renderStudio(agentPage(hrHelper.id));

  const detail = await screen.findByRole("region", { name: "Run of 2026-11-12 10:00 UTC" }, { timeout: 5000 });
  expect(detail).toHaveTextContent("judged by openai gpt-4.1-mini · 3 repeats");
  expect(within(detail).getByText("Evaluation score: 50%")).toBeInTheDocument();
  expect(detail).toHaveTextContent("1 passed, 1 failed, 1 Error left out of the score");
  const cases = within(detail).getByRole("list", { name: "Cases" });
  const [leave, parking, errored] = within(cases)
    .getAllByRole("listitem")
    .filter((item) => item.parentElement === cases);
  expect(within(leave as HTMLElement).getByLabelText("Result")).toHaveTextContent("PassUnsteady2/3 repeats passed");
  expect(leave).toHaveTextContent("Repeat 1: Pass");
  expect(leave).toHaveTextContent("Repeat 2: Fail");
  expect(within(parking as HTMLElement).getByLabelText("Result")).toHaveTextContent("Fail0/2 repeats passed");
  expect(parking).toHaveTextContent("Repeat 3: Error");
  expect(within(errored as HTMLElement).getByLabelText("Result")).toHaveTextContent("ErrorEvery repeat errored; left out of the score.");
});

// Two-sided Runs

const publishedHelper = { ...hrHelper, live_version: { id: agentVersion(2).id, number: 2 } };

function setUpPublished(options: Parameters<typeof fakeEvaluationApi>[0] = {}) {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi({
    versions: {
      [hrProject.id]: { current_version_id: instructionsVersion(2).id, versions: [instructionsVersion(2), instructionsVersion(1)] },
    },
  });
  fakeAgentsApi({ agents: [publishedHelper], versions: { [hrHelper.id]: [agentVersion(2), agentVersion(1)] } });
  return fakeEvaluationApi(options);
}

const twoSided = (id: string, overrides: Partial<ReturnType<typeof run>> = {}) =>
  run(id, "completed", 6, 6, { sides: [liveSide, draftSide], ...overrides });

const onSide = (result: typeof passed, position: string) => ({ ...result, position });

test("Evaluate compares the Live Version with the Draft by default; any two sides and the Draft's Instructions can be chosen", async () => {
  const user = userEvent.setup();
  const runId = "r6000000-0000-4000-8000-000000000006";
  const { requests } = setUpPublished({ cases: [leaveCase], started: [results(twoSided(runId), [])] });
  renderStudio(agentPage(hrHelper.id));
  await caseRows();

  await user.click(screen.getByRole("button", { name: "Evaluate" }));
  const dialog = await screen.findByRole("dialog", { name: "Evaluate" });
  const first = within(dialog).getByLabelText("First side");
  const second = within(dialog).getByLabelText("Second side");
  await waitFor(() => {
    expect(first).toHaveDisplayValue("Version 2 (Live)");
  });
  expect(second).toHaveDisplayValue("Draft");
  const instructions = await within(dialog).findByLabelText("Draft's Instructions");
  await waitFor(() => {
    expect(instructions).toHaveDisplayValue("Current Instructions Version (v2)");
  });

  // The same side twice is refused before anything is sent.
  await user.selectOptions(second, "Version 2 (Live)");
  expect(within(dialog).getByText("Choose two different sides.")).toBeInTheDocument();
  expect(first).toHaveAccessibleDescription("Choose two different sides.");
  expect(within(dialog).getByRole("button", { name: "Start Run" })).toBeDisabled();
  // Two Versions: the Draft's Instructions don't apply.
  await user.selectOptions(second, "Version 1");
  expect(within(dialog).queryByLabelText("Draft's Instructions")).not.toBeInTheDocument();
  await user.selectOptions(first, "Draft");
  await user.selectOptions(within(dialog).getByLabelText("Draft's Instructions"), "Instructions Draft");
  await user.click(within(dialog).getByRole("button", { name: "Start Run" }));

  await waitFor(() => {
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  expect(requests.filter((request) => request.route === "start")).toEqual([
    {
      route: "start",
      body: {
        sides: [{ kind: "draft" }, { kind: "version", version_id: agentVersion(1).id }],
        instructions_draft: true,
        instructions_version_id: null,
      },
    },
  ]);
});

test("the Draft can answer with any Instructions Version chosen", async () => {
  const user = userEvent.setup();
  const runId = "r7000000-0000-4000-8000-000000000007";
  const { requests } = setUpPublished({ cases: [leaveCase], started: [results(twoSided(runId), [])] });
  renderStudio(agentPage(hrHelper.id));
  await caseRows();

  await user.click(screen.getByRole("button", { name: "Evaluate" }));
  const dialog = await screen.findByRole("dialog", { name: "Evaluate" });
  const instructions = within(dialog).getByLabelText("Draft's Instructions");
  await within(dialog).findByRole("option", { name: "Instructions v1" });
  await user.selectOptions(instructions, "Instructions v1");
  await user.click(within(dialog).getByRole("button", { name: "Start Run" }));

  await waitFor(() => {
    expect(requests.filter((request) => request.route === "start")).toEqual([
      {
        route: "start",
        body: {
          sides: [{ kind: "version", version_id: agentVersion(2).id }, { kind: "draft" }],
          instructions_draft: false,
          instructions_version_id: instructionsVersion(1).id,
        },
      },
    ]);
  });
});

test("a two-sided Run shows each side's score, then Regressions, then improvements, then the rest, with both sides' answers", async () => {
  const runId = "r8000000-0000-4000-8000-000000000008";
  const fixed = { ...parkingCase, question: "Fixed?" };
  const same = { ...parkingCase, question: "Same?" };
  const compared = results(twoSided(runId, { stale: true }), [
    [leaveCase, [onSide(passed, "first"), onSide(failedResult, "second")]],
    [fixed, [onSide(failedResult, "first"), onSide(passed, "second")]],
    [same, [onSide(passed, "first"), onSide(passed, "second")]],
  ]);
  const [broken, improved, rest] = compared.cases as [(typeof compared.cases)[number], (typeof compared.cases)[number], (typeof compared.cases)[number]];
  compared.cases = [
    { ...broken, change: "regression", sides: [caseSide("pass", 1, 1), { ...caseSide("fail", 0, 1), position: "second" }] },
    { ...improved, change: "improvement", sides: [caseSide("fail", 0, 1), { ...caseSide("pass", 1, 1), position: "second" }] },
    { ...rest, sides: [caseSide("pass", 1, 1), { ...caseSide("pass", 1, 1), position: "second" }] },
  ];
  setUpPublished({ cases: [leaveCase, fixed, same], runs: [compared] });
  renderStudio(agentPage(hrHelper.id));

  const runs = await screen.findByRole("list", { name: "Evaluation Runs" }, { timeout: 5000 });
  expect(runs).toHaveTextContent("Completed");
  expect(runs).toHaveTextContent("Stale");
  expect(runs).toHaveTextContent("Version 1: 67% · Draft revision 4: 33%");
  const detail = await screen.findByRole("region", { name: "Run of 2026-11-12 10:00 UTC" });
  expect(detail).toHaveTextContent(
    "Version 1 · Instructions v1 · openai gpt-4.1-mini against Draft revision 4 · Instructions Draft · openai gpt-4.1-mini",
  );
  expect(within(detail).getByRole("status")).toHaveTextContent("The Draft has changed since this Run");
  expect(within(detail).getByRole("group", { name: "Version 1" })).toHaveTextContent("First side: Version 1Evaluation score: 67%");
  expect(within(detail).getByRole("group", { name: "Draft revision 4" })).toHaveTextContent("Second side: Draft revision 4Evaluation score: 33%");
  expect(detail).toHaveTextContent("1 Regression and 1 improvement");

  const cases = within(detail).getByRole("list", { name: "Cases" });
  const items = within(cases).getAllByRole("listitem").filter((item) => item.parentElement === cases);
  expect(items.map((item) => within(item).getByLabelText("Result").textContent)).toEqual([
    "RegressionVersion 1:Pass1/1 repeats passedDraft revision 4:Fail0/1 repeats passed",
    "ImprovementVersion 1:Fail0/1 repeats passedDraft revision 4:Pass1/1 repeats passed",
    "Version 1:Pass1/1 repeats passedDraft revision 4:Pass1/1 repeats passed",
  ]);
  const regression = items[0] as HTMLElement;
  expect(within(regression).getByRole("group", { name: "Answers of Version 1" })).toHaveTextContent("Repeat 1: Pass");
  expect(within(regression).getByRole("group", { name: "Answers of Draft revision 4" })).toHaveTextContent(
    `Repeat 1: FailAnswer${failedResult.answer ?? ""}`,
  );
});

test("a two-sided Run with a side that has no score and several of each change says so", async () => {
  const runId = "r9000000-0000-4000-8000-000000000009";
  const compared = results(twoSided(runId, { sides: [{ ...liveSide, score: null }, draftSide] }), []);
  setUpPublished({ cases: [leaveCase], runs: [compared] });
  renderStudio(agentPage(hrHelper.id));

  const runs = await screen.findByRole("list", { name: "Evaluation Runs" }, { timeout: 5000 });
  expect(runs).toHaveTextContent("Version 1: no score");
  const detail = await screen.findByRole("region", { name: "Run of 2026-11-12 10:00 UTC" });
  expect(detail).toHaveTextContent("0 Regressions and 0 improvements");
});

test("a running Run can be cancelled; it keeps what it answered", async () => {
  const user = userEvent.setup();
  const runId = "ra000000-0000-4000-8000-00000000000a";
  const { requests } = setUpPublished({
    cases: [leaveCase],
    runs: [results(run(runId, "running", 1, 2, { sides: [liveSide, draftSide] }), [[leaveCase, [onSide(passed, "first")]]])],
  });
  renderStudio(agentPage(hrHelper.id));

  const runs = await screen.findByRole("list", { name: "Evaluation Runs" }, { timeout: 5000 });
  expect(runs).toHaveTextContent("Version 1: running · Draft revision 4: running");
  expect(screen.getByRole("button", { name: "Evaluating…" })).toBeDisabled();
  await user.click(await screen.findByRole("button", { name: "Cancel Run" }));

  const detail = await screen.findByRole("region", { name: "Run of 2026-11-12 10:00 UTC" });
  expect(await within(detail).findByText("This Run was cancelled. The answers it gave before stopping are kept.")).toBeInTheDocument();
  expect(detail).toHaveTextContent("Cancelled");
  expect(within(detail).queryByRole("button", { name: "Cancel Run" })).not.toBeInTheDocument();
  expect(requests.filter((request) => request.route === "cancel")).toEqual([{ route: "cancel", body: { runId } }]);
  expect(await screen.findByRole("button", { name: "Evaluate" })).toBeEnabled();
});

test("a refused cancel says why", async () => {
  const user = userEvent.setup();
  const runId = "rb000000-0000-4000-8000-00000000000b";
  setUpPublished({
    cases: [leaveCase],
    runs: [results(run(runId, "running", 0, 2), [])],
    cancelStatus: 409,
    cancelDetail: "This Run has already finished.",
  });
  renderStudio(agentPage(hrHelper.id));

  await user.click(await screen.findByRole("button", { name: "Cancel Run" }, { timeout: 5000 }));

  const detail = await screen.findByRole("region", { name: "Run of 2026-11-12 10:00 UTC" });
  expect(await within(detail).findByRole("alert")).toHaveTextContent("This Run has already finished.");
});

test("an archived Agent's running Run can't be cancelled from the Studio", async () => {
  setUp({ cases: [leaveCase], runs: [results(run("rc000000-0000-4000-8000-00000000000c", "running", 0, 1), [])] }, [oldHelper]);
  renderStudio(agentPage(oldHelper.id));

  expect(await screen.findByRole("meter", { name: "Answers given" }, { timeout: 5000 })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Cancel Run" })).not.toBeInTheDocument();
});
