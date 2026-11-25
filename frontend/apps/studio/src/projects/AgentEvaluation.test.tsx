import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { agentVersion, fakeAgentsApi, hrHelper, hrTrace, oldHelper } from "../test/agents";
import { adaSession, fakeAuthApi } from "../test/auth";
import {
  anEstimate,
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
  verdict,
} from "../test/evaluation";
import { aChunk, aDocument, fakeDocumentViewerApi } from "../test/documents";
import { openSection } from "../test/navigation";
import { fakeProjectsApi, hrProject, instructionsVersion } from "../test/projects";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

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
    {
      route: "create",
      body: {
        question: "How much leave do I get?",
        reference_answer: "Everyone gets 25 days.",
        expected_sources: [],
        expect_fallback: false,
        source: "written",
      },
    },
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
  expect(screen.queryByRole("meter", { name: "Answers given" })).not.toBeInTheDocument();
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

test("the Evaluate dialog shows the estimated Cost before starting, asked again as the sides change", async () => {
  const user = userEvent.setup();
  const { estimates } = setUpPublished({ cases: [leaveCase] });
  renderStudio(agentPage(hrHelper.id));
  await caseRows();

  await user.click(screen.getByRole("button", { name: "Evaluate" }));
  const dialog = await screen.findByRole("dialog", { name: "Evaluate" });
  const estimate = within(dialog).getByRole("status", { name: "Estimated Cost" });

  await waitFor(() => {
    expect(estimate).toHaveTextContent("About $0.006: answers $0.004, judging $0.002");
  });
  expect(dialog).toHaveTextContent(
    "2 cases × 1 side × 1 repeat, at each side's mean Cost per reply over the last 30 days, plus judging every answer. The Run records what it actually costs.",
  );
  // The same side twice asks nothing.
  await user.selectOptions(within(dialog).getByLabelText("Second side"), "Version 2 (Live)");
  expect(estimate).toHaveTextContent("Choose two different sides to see the estimated Cost.");
  await user.selectOptions(within(dialog).getByLabelText("Second side"), "None: the first side runs alone");
  await waitFor(() => {
    expect(estimates.at(-1)).toEqual({
      sides: [{ kind: "version", version_id: agentVersion(2).id }],
      instructions_draft: false,
      instructions_version_id: null,
    });
  });
});

test("an estimate of one case on two sides counts them", async () => {
  const user = userEvent.setup();
  setUpPublished({ cases: [leaveCase], estimate: { ...anEstimate, cases: 1, sides: 2, repeats: 3 } });
  renderStudio(agentPage(hrHelper.id));
  await caseRows();
  await user.click(screen.getByRole("button", { name: "Evaluate" }));
  const dialog = await screen.findByRole("dialog", { name: "Evaluate" });
  await waitFor(() => {
    expect(dialog).toHaveTextContent("1 case × 2 sides × 3 repeats");
  });
});

test("an estimate that can't be priced says so", async () => {
  const user = userEvent.setup();
  setUp({ cases: [leaveCase], estimate: { ...anEstimate, answers_usd: null, total_usd: null } });
  renderStudio(agentPage(hrHelper.id));
  await caseRows();
  await user.click(screen.getByRole("button", { name: "Evaluate" }));
  const priced = await screen.findByRole("status", { name: "Estimated Cost" });
  await waitFor(() => {
    expect(priced).toHaveTextContent("The Cost can't be estimated: a model this Run uses has no price set.");
  });
});

test("a refused estimate says why", async () => {
  const user = userEvent.setup();
  setUp({ cases: [leaveCase], estimate: { status: 409, detail: "Add an Evaluation Case before evaluating." } });
  renderStudio(agentPage(hrHelper.id));
  await caseRows();
  await user.click(screen.getByRole("button", { name: "Evaluate" }));
  const refused = await screen.findByRole("status", { name: "Estimated Cost" });
  await waitFor(() => {
    expect(refused).toHaveTextContent("The Cost could not be estimated. Add an Evaluation Case before evaluating.");
  });
});

test("Run detail shows the sides, failing Verdicts with reasons, and each answer's Trace", async () => {
  const user = userEvent.setup();
  setUp({ cases: [leaveCase, parkingCase], runs: [finished] });
  renderStudio(agentPage(hrHelper.id));

  const runs = await screen.findByRole("list", { name: "Evaluation Runs" }, { timeout: 5000 });
  expect(within(runs).getByRole("button", { name: "Run of 2026-11-12 10:00 UTC" })).toHaveAttribute("aria-current", "true");
  expect(runs).toHaveTextContent("Completed");
  expect(runs).toHaveTextContent("2 / 2 answers");
  // The history list shows each Run's Cost.
  expect(runs).toHaveTextContent("Cost $0.006");
  const detail = await screen.findByRole("region", { name: "Run of 2026-11-12 10:00 UTC" });
  expect(detail).toHaveTextContent(
    "Completed · Draft revision 3 · Instructions v2 · openai gpt-4.1-mini · judged by openai gpt-4.1-mini",
  );
  // Its actual Cost, split into answers and judging, beside what it was estimated at.
  expect(detail).toHaveTextContent("Cost $0.006: answers $0.0042, judging $0.0018 (estimated $0.006)");
  const cases = within(detail).getByRole("list", { name: "Cases" });
  const parking = within(cases).getAllByRole("listitem").filter((item) => item.parentElement === cases)[1] as HTMLElement;
  expect(parking).toHaveTextContent("Repeat 1: Fail");
  expect(parking).toHaveTextContent("Reference answer: In the north car park.");
  expect(
    within(within(parking).getByRole("list", { name: "Verdicts" }))
      .getAllByRole("listitem")
      .map((item) => item.firstElementChild?.textContent),
  ).toEqual(["Reference answer: Fail. The answer doesn't name the north car park.", "Grounding: Fail. Nothing cited supports it."]);

  const trace = within(parking).getByRole("group", { name: "Trace" });
  await user.click(within(trace).getByText("Trace"));
  expect(await within(trace).findByRole("table", { name: "Retrieved Chunks" })).toBeInTheDocument();
  expect(trace).toHaveTextContent("Instructionsv2");
});

test("a Run that failed says why; a Run without Project Instructions says so", async () => {
  const failedRun = run("r3000000-0000-4000-8000-000000000003", "failed", 1, 1, {
    error_message: "Every case errored.",
    // Started when a model's price wasn't set: no estimate, and nothing priced was spent.
    cost: { estimated_usd: null, answers_usd: "0", judging_usd: "0", total_usd: "0" },
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
  expect(detail).toHaveTextContent("Cost $0.00: answers $0.00, judging $0.00 (no estimate)");
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

test("Run detail shows the Judging setup it was judged under in its header", async () => {
  const runId = "r5000000-0000-4000-8000-000000000015";
  const guided = results(run(runId, "completed", 1, 1, { judging_guidance_version: 2 }), [[leaveCase, [repeat(passed, 1)], caseSide("pass", 1, 1, 1)]]);
  setUp({ cases: [leaveCase], runs: [guided] });
  renderStudio(agentPage(hrHelper.id));

  const detail = await screen.findByRole("region", { name: "Run of 2026-11-12 10:00 UTC" }, { timeout: 5000 });
  expect(detail).toHaveTextContent("judged by openai gpt-4.1-mini with guidance version 2 · 1 repeat");
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
  // Its Judging setup: the judge model, and no Judging guidance.
  expect(detail).toHaveTextContent("judged by openai gpt-4.1-mini with no guidance · 3 repeats");
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

// Expected sources and Expect Fallback Text

const leaveDocument = aDocument({ id: "d0c00000-0000-4000-8000-000000000009", name: "leave.txt", chunk_count: 2 });
const leaveChunks = [
  aChunk({ ordinal: 0, text: "Everyone gets 25 days of annual leave a year." }),
  aChunk({ ordinal: 1, text: "Leave carries over until March." }),
];

async function openNewCase(user: ReturnType<typeof userEvent.setup>) {
  const set = await setRegion();
  await user.click(within(set).getAllByRole("button", { name: "New case" })[0] as HTMLElement);
  return screen.findByRole("dialog", { name: "New Evaluation Case" });
}

test("an Editor picks a passage from a Document's Chunks as an Expected source", async () => {
  const user = userEvent.setup();
  const { requests } = setUp({ documentNames: { [leaveDocument.id]: "leave.txt" } });
  fakeDocumentViewerApi({ document: { ...leaveDocument, markdown: "" }, chunks: leaveChunks });
  renderStudio(agentPage(hrHelper.id));
  const editor = await openNewCase(user);
  await user.type(within(editor).getByLabelText("Question"), "How much leave do I get?");
  expect(within(editor).getByText("No Expected sources.")).toBeInTheDocument();

  await user.click(within(editor).getByRole("button", { name: "Add Expected source" }));
  const picker = within(editor).getByRole("group", { name: "Pick a passage" });
  // Adding without a Document and passage says what's missing.
  await user.click(within(picker).getByRole("button", { name: "Add passage" }));
  expect(within(picker).getByLabelText("Passage")).toHaveAccessibleDescription(/Choose a Document and a passage of it./);
  await user.selectOptions(await within(picker).findByLabelText("Document"), "leave.txt");
  const chunks = await within(picker).findByRole("list", { name: "Chunks" });
  expect(within(chunks).getAllByRole("listitem")).toHaveLength(2);
  await user.click(within(chunks).getByRole("button", { name: "Use Chunk 1 as the passage" }));
  const passage = within(picker).getByLabelText("Passage");
  expect(passage).toHaveValue("Everyone gets 25 days of annual leave a year.");
  // Trimmed to the words that matter.
  await user.clear(passage);
  await user.type(passage, "25 days of annual leave");
  await user.click(within(picker).getByRole("button", { name: "Add passage" }));

  const sources = within(editor).getByRole("list", { name: "Expected sources" });
  expect(sources).toHaveTextContent("leave.txt“25 days of annual leave”");
  // A case with an Expected source needs nothing else.
  await user.click(within(editor).getByRole("button", { name: "Save case" }));
  await waitFor(() => {
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  expect(requests).toEqual([
    {
      route: "create",
      body: {
        question: "How much leave do I get?",
        reference_answer: "",
        expected_sources: [{ document_id: leaveDocument.id, passage: "25 days of annual leave" }],
        expect_fallback: false,
        source: "written",
      },
    },
  ]);
  expect(await caseRows()).toEqual([["How much leave do I get?", "leave.txt: “25 days of annual leave”"]]);
});

test("the picker can be cancelled, and a Project without Ready Documents says so", async () => {
  const user = userEvent.setup();
  setUp();
  fakeDocumentViewerApi({ document: { ...leaveDocument, status: "processing", markdown: null }, chunks: [] });
  renderStudio(agentPage(hrHelper.id));
  const editor = await openNewCase(user);

  await user.click(within(editor).getByRole("button", { name: "Add Expected source" }));
  expect(await within(editor).findByText("This Project has no Ready Documents yet. Upload one in Documents first.")).toBeInTheDocument();
  await user.type(within(editor).getByLabelText("Passage"), "anything");
  await user.click(within(editor).getByRole("button", { name: "Cancel picking" }));
  expect(within(editor).queryByRole("group", { name: "Pick a passage" })).not.toBeInTheDocument();
});

test("a Document with no Chunks, or Chunks that can't be loaded, says so in the picker", async () => {
  const user = userEvent.setup();
  setUp();
  fakeDocumentViewerApi({ document: { ...leaveDocument, markdown: "" }, chunks: [] });
  renderStudio(agentPage(hrHelper.id));
  const editor = await openNewCase(user);
  await user.click(within(editor).getByRole("button", { name: "Add Expected source" }));
  await user.selectOptions(await within(editor).findByLabelText("Document"), "leave.txt");
  expect(await within(editor).findByText("This Document has no Chunks yet.")).toBeInTheDocument();

  server.use(
    http.get("*/api/organisations/:organisationId/projects/:projectId/documents/:documentId/chunks", () =>
      HttpResponse.json({ detail: "Down" }, { status: 500 }),
    ),
    http.get("*/api/organisations/:organisationId/projects/:projectId/documents", () =>
      HttpResponse.json({ detail: "Down" }, { status: 500 }),
    ),
  );
  await user.click(within(editor).getByRole("button", { name: "Cancel picking" }));
  await user.click(within(editor).getByRole("button", { name: "Cancel" }));
  const again = await openNewCase(user);
  await user.click(within(again).getByRole("button", { name: "Add Expected source" }));
  await user.selectOptions(await within(again).findByLabelText("Document"), "leave.txt");
  expect(await within(again).findByText("The Chunks could not be loaded. Try again shortly.")).toBeInTheDocument();
});

test("a long Document's Chunks are paged in the picker", async () => {
  const user = userEvent.setup();
  setUp();
  const many = Array.from({ length: 51 }, (_, ordinal) => aChunk({ ordinal, text: `Chunk text ${String(ordinal + 1)}.` }));
  fakeDocumentViewerApi({ document: { ...leaveDocument, chunk_count: 51, markdown: "" }, chunks: many });
  renderStudio(agentPage(hrHelper.id));
  const editor = await openNewCase(user);
  await user.click(within(editor).getByRole("button", { name: "Add Expected source" }));
  await user.selectOptions(await within(editor).findByLabelText("Document"), "leave.txt");
  await within(editor).findByRole("list", { name: "Chunks" });

  await user.click(within(editor).getByRole("button", { name: "Page 2" }));
  await user.click(await within(editor).findByRole("button", { name: "Use Chunk 51 as the passage" }));
  expect(within(editor).getByLabelText("Passage")).toHaveValue("Chunk text 51.");
});

test("Documents that can't be loaded say so in the picker", async () => {
  const user = userEvent.setup();
  setUp();
  server.use(
    http.get("*/api/organisations/:organisationId/projects/:projectId/documents", () =>
      HttpResponse.json({ detail: "Down" }, { status: 500 }),
    ),
  );
  renderStudio(agentPage(hrHelper.id));
  const editor = await openNewCase(user);
  await user.click(within(editor).getByRole("button", { name: "Add Expected source" }));
  expect(await within(editor).findByText("The Documents could not be loaded. Try again shortly.", undefined, { timeout: 5000 })).toBeInTheDocument();
});

test("Expect Fallback Text stands alone: combined with a Reference answer or an Expected source, the refusal names the field", async () => {
  const user = userEvent.setup();
  const { requests } = setUp({ cases: [staleCase] });
  renderStudio(agentPage(hrHelper.id));
  await caseRows();
  const editor = await openNewCase(user);
  await user.type(within(editor).getByLabelText("Question"), "What is on the canteen menu?");
  const fallback = within(editor).getByLabelText("Expect Fallback Text");
  await user.click(fallback);
  await user.type(within(editor).getByLabelText("Reference answer"), "Soup.");
  await user.click(within(editor).getByRole("button", { name: "Save case" }));
  expect(fallback).toHaveAttribute("aria-invalid", "true");
  expect(fallback).toHaveAccessibleDescription(/can't be combined with a Reference answer/);

  await user.clear(within(editor).getByLabelText("Reference answer"));
  await user.click(within(editor).getByRole("button", { name: "Save case" }));
  await waitFor(() => {
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  expect(requests).toEqual([
    {
      route: "create",
      body: { question: "What is on the canteen menu?", reference_answer: "", expected_sources: [], expect_fallback: true, source: "written" },
    },
  ]);
  const rows = await caseRows();
  expect(rows[1]).toEqual(["What is on the canteen menu?", "Expects the Fallback Text."]);

  // The stale case keeps its Expected sources: ticking Expect Fallback Text is refused, naming them.
  await user.click(screen.getByRole("button", { name: `More actions for ${staleCase.question}` }));
  await user.click(screen.getByRole("menuitem", { name: "Edit" }));
  const editing = await screen.findByRole("dialog", { name: "Edit Evaluation Case" });
  await user.click(within(editing).getByLabelText("Expect Fallback Text"));
  await user.click(within(editing).getByRole("button", { name: "Save case" }));
  expect(within(editing).getByLabelText("Expect Fallback Text")).toHaveAccessibleDescription(
    /can't be combined with an Expected source/,
  );
});

const staleCase = {
  ...leaveCase,
  id: "e1000000-0000-4000-8000-000000000003",
  question: "Who approves leave?",
  reference_answer: null,
  stale: true,
  expected_sources: [
    {
      id: "e3000000-0000-4000-8000-000000000001",
      document_id: leaveDocument.id,
      document_name: "leave.txt",
      passage: "25 days",
      stale: false,
      stale_reason: null,
    },
    {
      id: "e3000000-0000-4000-8000-000000000002",
      document_id: null,
      document_name: "parking.txt",
      passage: "north car park",
      stale: true,
      stale_reason: "document_deleted",
    },
  ],
};

test("a case with a Stale expectation is flagged in the set, and its deleted Document's source must be removed before saving", async () => {
  const user = userEvent.setup();
  const missing = { ...staleCase.expected_sources[0], stale: true, stale_reason: "passage_missing" } as (typeof staleCase.expected_sources)[number];
  const { requests } = setUp({ cases: [staleCase, { ...parkingCase, stale: true, expected_sources: [missing] }] });
  renderStudio(agentPage(hrHelper.id));

  const table = await screen.findByRole("table", { name: "Evaluation Cases" }, { timeout: 5000 });
  const [first, second] = within(table).getAllByRole("row").slice(1) as [HTMLElement, HTMLElement];
  expect(within(first).getByText("Stale expectation")).toHaveAttribute("title", "Its Document has been deleted.");
  expect(within(second).getByText("Stale expectation")).toHaveAttribute(
    "title",
    "No Chunk of its Document's current Edition holds this passage.",
  );

  await user.click(screen.getByRole("button", { name: `More actions for ${staleCase.question}` }));
  await user.click(screen.getByRole("menuitem", { name: "Edit" }));
  const editor = await screen.findByRole("dialog", { name: "Edit Evaluation Case" });
  const sources = within(editor).getByRole("list", { name: "Expected sources" });
  expect(sources).toHaveTextContent("Its Document has been deleted.");
  await user.click(within(editor).getByRole("button", { name: "Save case" }));
  expect(within(editor).getByRole("group", { name: "Expected sources" })).toHaveAccessibleDescription(
    "Remove the Expected sources whose Document has been deleted, then save.",
  );
  expect(requests).toEqual([]);

  await user.click(within(sources).getByRole("button", { name: "Remove the passage of parking.txt" }));
  await user.click(within(editor).getByRole("button", { name: "Save case" }));
  await waitFor(() => {
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  expect(requests[0]?.body).toMatchObject({ expected_sources: [{ document_id: leaveDocument.id, passage: "25 days" }] });
});

test("Run detail shows Expected source and fallback Verdicts, Stale ones skipped, and flags the case", async () => {
  const checked: typeof passed = {
    ...passed,
    verdicts: [
      verdict("expected_source", "pass", "The answer cited the passage of leave.txt."),
      verdict("expected_source", "stale", "parking.txt has been deleted, so this was skipped."),
      verdict("grounding", "pass", "Every claim is in the cited excerpt."),
    ],
  };
  const fallbackCase = { ...parkingCase, reference_answer: null, expect_fallback: true };
  const fallbackResult: typeof passed = {
    ...failedResult,
    verdicts: [verdict("fallback", "fail", "The answer wasn't the Fallback Text or the Refusal text.")],
  };
  setUp({
    cases: [staleCase, fallbackCase],
    runs: [
      results(run("r3000000-0000-4000-8000-000000000003", "completed", 2, 2), [
        [staleCase, checked],
        [fallbackCase, fallbackResult],
      ]),
    ],
  });
  renderStudio(agentPage(hrHelper.id));

  const detail = await screen.findByRole("region", { name: "Run of 2026-11-12 10:00 UTC" }, { timeout: 5000 });
  const cases = within(detail).getByRole("list", { name: "Cases" });
  const [stale, fallback] = within(cases).getAllByRole("listitem").filter((item) => item.parentElement === cases) as [
    HTMLElement,
    HTMLElement,
  ];
  expect(stale).toHaveTextContent("Stale expectation");
  expect(stale).toHaveTextContent("An Expected source's Document or passage is gone, so it was skipped: neither pass nor fail.");
  expect(stale).not.toHaveTextContent("Reference answer:");
  expect(within(stale).getByRole("list", { name: "Expected sources" })).toHaveTextContent(
    "leave.txt: “25 days”parking.txt: “north car park”",
  );
  expect(within(stale).getByRole("list", { name: "Verdicts" })).toHaveTextContent(
    "Expected source: Pass. The answer cited the passage of leave.txt." +
      "Expected source: Stale, skipped. parking.txt has been deleted, so this was skipped." +
      "Grounding: Pass. Every claim is in the cited excerpt.",
  );
  expect(fallback).toHaveTextContent("Expects the Fallback Text.");
  expect(fallback).not.toHaveTextContent("Stale expectation");
  expect(within(fallback).getByRole("list", { name: "Verdicts" })).toHaveTextContent(
    "Expect Fallback Text: Fail. The answer wasn't the Fallback Text or the Refusal text.",
  );
});

// Building the set

const unsteadyLatest = {
  run_id: "r1000000-0000-4000-8000-000000000001",
  outcome: "pass",
  passed: 2,
  answered: 3,
  repeats: 3,
  unsteady: true,
};

test("the set is searched and filtered by expectation kind, Stale flag and latest result", async () => {
  const user = userEvent.setup();
  setUp({
    cases: [
      leaveCase,
      { ...parkingCase, latest_result: unsteadyLatest },
      staleCase,
      { ...parkingCase, id: "e1000000-0000-4000-8000-000000000006", question: "Canteen menu?", reference_answer: null, expect_fallback: true },
    ],
  });
  renderStudio(agentPage(hrHelper.id));
  const questions = async () => (await caseRows()).map(([question]) => question);
  expect(await questions()).toEqual([leaveCase.question, parkingCase.question, staleCase.question, "Canteen menu?"]);
  const search = screen.getByRole("search");

  await user.type(within(search).getByRole("searchbox", { name: "Search the questions" }), "LEAVE");
  await waitFor(async () => {
    expect(await questions()).toEqual([leaveCase.question, staleCase.question]);
  });
  await user.selectOptions(within(search).getByLabelText("Stale expectation"), "Stale expectation");
  await waitFor(async () => {
    expect(await questions()).toEqual([staleCase.question]);
  });
  await user.click(within(search).getByRole("button", { name: "Clear filters" }));
  await user.selectOptions(within(search).getByLabelText("Expectation"), "Expect Fallback Text");
  await waitFor(async () => {
    expect(await questions()).toEqual(["Canteen menu?"]);
  });
  await user.selectOptions(within(search).getByLabelText("Expectation"), "Any expectation");
  await user.selectOptions(within(search).getByLabelText("Stale expectation"), "No Stale expectation");
  await user.click(within(search).getByRole("radio", { name: "Unsteady" }));
  await waitFor(async () => {
    expect(await questions()).toEqual([parkingCase.question]);
  });

  // Nothing matches: the set says so, and Evaluate still answers the whole set.
  await user.click(within(search).getByRole("radio", { name: "Error" }));
  expect(await screen.findByRole("heading", { name: "No cases match" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Evaluate" })).toBeEnabled();
  await user.click(within(search).getByRole("button", { name: "Clear filters" }));
  expect(await questions()).toHaveLength(4);
  expect(within(search).queryByRole("button", { name: "Clear filters" })).not.toBeInTheDocument();
});

test("a set that can't be filtered says so", async () => {
  const user = userEvent.setup();
  setUp({ cases: [leaveCase] });
  renderStudio(agentPage(hrHelper.id));
  await caseRows();
  server.use(
    http.get("*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/evaluation/cases", ({ request }) =>
      new URL(request.url).searchParams.has("q") ? HttpResponse.json({ detail: "Down" }, { status: 500 }) : undefined,
    ),
  );

  await user.type(screen.getByRole("searchbox", { name: "Search the questions" }), "x");

  expect(await screen.findByText("The Evaluation Set could not be filtered. Try again shortly.")).toBeInTheDocument();
});

const expensesHelper = { ...hrHelper, id: "a9e00000-0000-4000-8000-000000000002", name: "Expenses helper" };
const expensesCases = [
  { ...leaveCase, id: "e5000000-0000-4000-8000-000000000001", question: "Can I claim a taxi?" },
  { ...parkingCase, id: "e5000000-0000-4000-8000-000000000002", question: "When are claims paid?" },
];

test("cases are copied from another Agent of the Project, as many as are ticked", async () => {
  const user = userEvent.setup();
  const { requests } = setUp({ cases: [leaveCase], otherCases: { [expensesHelper.id]: expensesCases } }, [hrHelper, expensesHelper]);
  renderStudio(agentPage(hrHelper.id));
  await caseRows();

  await user.click(screen.getByRole("button", { name: "Copy from another Agent" }));
  const dialog = await screen.findByRole("dialog", { name: "Copy from another Agent" });
  expect(within(dialog).getByRole("button", { name: "Copy 0 cases" })).toBeDisabled();
  // The Agent itself isn't offered.
  const agentChoice = within(dialog).getByLabelText("Agent");
  expect(within(agentChoice).getAllByRole("option").map((option) => option.textContent)).toEqual(["Choose an Agent", "Expenses helper"]);
  await user.selectOptions(agentChoice, "Expenses helper");
  await user.click(await within(dialog).findByLabelText("Select all (2)"));
  expect(within(dialog).getByRole("button", { name: "Copy 2 cases" })).toBeEnabled();
  await user.click(within(dialog).getByLabelText("Select all (2)"));
  // A case ticked by mistake is unticked again.
  await user.click(within(dialog).getByLabelText("Can I claim a taxi?"));
  await user.click(within(dialog).getByLabelText("Can I claim a taxi?"));
  await user.click(within(dialog).getByLabelText("When are claims paid?"));
  await user.click(within(dialog).getByRole("button", { name: "Copy 1 case" }));

  expect(await screen.findByText("Copied 1 case.")).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(requests.filter((request) => request.route === "copy")).toEqual([
    { route: "copy", body: { agent_id: expensesHelper.id, case_ids: [expensesCases[1]?.id] } },
  ]);
  await waitFor(async () => {
    expect((await caseRows()).map(([question]) => question)).toEqual([leaveCase.question, "When are claims paid?"]);
  });
});

test("copying several cases says how many; a refused copy says why", async () => {
  const user = userEvent.setup();
  const refusal = "An Evaluation Set holds at most 200 cases, and this one has 199. Delete cases before adding more.";
  setUp({ cases: [leaveCase], otherCases: { [expensesHelper.id]: expensesCases }, copyStatus: 409, copyDetail: refusal }, [hrHelper, expensesHelper]);
  renderStudio(agentPage(hrHelper.id));
  await caseRows();

  await user.click(screen.getByRole("button", { name: "Copy from another Agent" }));
  const dialog = await screen.findByRole("dialog", { name: "Copy from another Agent" });
  await user.selectOptions(within(dialog).getByLabelText("Agent"), "Expenses helper");
  await user.click(await within(dialog).findByLabelText("Select all (2)"));
  await user.click(within(dialog).getByRole("button", { name: "Copy 2 cases" }));

  expect(await within(dialog).findByRole("alert")).toHaveTextContent(refusal);
});

test("copied cases are counted in the toast", async () => {
  const user = userEvent.setup();
  setUp({ cases: [leaveCase], otherCases: { [expensesHelper.id]: expensesCases } }, [hrHelper, expensesHelper]);
  renderStudio(agentPage(hrHelper.id));
  await caseRows();

  await user.click(screen.getByRole("button", { name: "Copy from another Agent" }));
  const dialog = await screen.findByRole("dialog", { name: "Copy from another Agent" });
  await user.selectOptions(within(dialog).getByLabelText("Agent"), "Expenses helper");
  await user.click(await within(dialog).findByLabelText("Select all (2)"));
  await user.click(within(dialog).getByRole("button", { name: "Copy 2 cases" }));

  expect(await screen.findByText("Copied 2 cases.")).toBeInTheDocument();
});

test("copying says when there's no other Agent, an empty set, or one that can't be loaded", async () => {
  const user = userEvent.setup();
  const emptyHelper = { ...expensesHelper, id: "a9e00000-0000-4000-8000-000000000004", name: "Empty helper" };
  setUp({ cases: [leaveCase], otherCases: { [emptyHelper.id]: [] } }, [hrHelper]);
  renderStudio(agentPage(hrHelper.id));
  await caseRows();

  await user.click(screen.getByRole("button", { name: "Copy from another Agent" }));
  const alone = await screen.findByRole("dialog", { name: "Copy from another Agent" });
  expect(await within(alone).findByText("This Project has no other Agent to copy from.")).toBeInTheDocument();
  await user.click(within(alone).getByRole("button", { name: "Cancel" }));

  server.use(
    http.get("*/api/organisations/:organisationId/projects/:projectId/agents", () =>
      HttpResponse.json([hrHelper, emptyHelper, expensesHelper]),
    ),
    http.get(`*/api/organisations/:organisationId/projects/:projectId/agents/${expensesHelper.id}/evaluation/cases`, () =>
      HttpResponse.json({ detail: "Down" }, { status: 500 }),
    ),
  );
  await user.click(screen.getByRole("button", { name: "Copy from another Agent" }));
  const dialog = await screen.findByRole("dialog", { name: "Copy from another Agent" });
  await user.selectOptions(await within(dialog).findByLabelText("Agent"), "Empty helper");
  expect(await within(dialog).findByText("That Agent's Evaluation Set is empty.")).toBeInTheDocument();
  await user.selectOptions(within(dialog).getByLabelText("Agent"), "Expenses helper");
  expect(await within(dialog).findByText("That Agent's Evaluation Set could not be loaded. Try again shortly.")).toBeInTheDocument();
});

test("copying says when the Project's Agents can't be loaded", async () => {
  const user = userEvent.setup();
  setUp({ cases: [leaveCase] });
  server.use(
    http.get("*/api/organisations/:organisationId/projects/:projectId/agents", () => HttpResponse.json({ detail: "Down" }, { status: 500 })),
  );
  renderStudio(agentPage(hrHelper.id));
  await caseRows();

  await user.click(screen.getByRole("button", { name: "Copy from another Agent" }));

  const dialog = await screen.findByRole("dialog", { name: "Copy from another Agent" });
  expect(await within(dialog).findByText("The Agents could not be loaded. Try again shortly.")).toBeInTheDocument();
  expect(within(dialog).queryByLabelText("Agent")).not.toBeInTheDocument();
});

test("a full set of 200 cases says so, and New case and Copy wait until cases are deleted", async () => {
  const many = Array.from({ length: 200 }, (_, index) => ({
    ...leaveCase,
    id: `e6000000-0000-4000-8000-${String(index).padStart(12, "0")}`,
    question: `Question ${String(index + 1)}?`,
  }));
  setUp({ cases: many });
  renderStudio(agentPage(hrHelper.id));
  await caseRows();

  expect(screen.getByRole("meter", { name: "Cases in the set" })).toHaveAttribute("aria-valuenow", "200");
  expect(screen.getByText(/holds the most it can, 200 cases/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "New case" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Copy from another Agent" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Evaluate" })).toBeEnabled();
});

test("a Suggestion's check is in the Run history: the Live Version against the Suggestion", async () => {
  const runId = "ra000000-0000-4000-8000-00000000000b";
  const suggestionSide = { ...liveSide, position: "second", kind: "suggestion", score: 2 / 3 };
  const check = results(twoSided(runId, { kind: "suggestion", sides: [liveSide, suggestionSide] }), []);
  setUpPublished({ cases: [leaveCase], runs: [check] });
  renderStudio(agentPage(hrHelper.id));

  const runs = await screen.findByRole("list", { name: "Evaluation Runs" }, { timeout: 5000 });
  expect(runs).toHaveTextContent("Suggestion's check");
  expect(runs).toHaveTextContent("Version 1: 67% · Suggestion on Version 1: 67%");
  const detail = await screen.findByRole("region", { name: "Run of 2026-11-12 10:00 UTC" });
  expect(detail).toHaveTextContent(
    "Version 1 · Instructions v1 · openai gpt-4.1-mini against Suggestion on Version 1 · Instructions v1 · openai gpt-4.1-mini",
  );
});

test("a Rollout evaluation is in the Run history: the Live Version against its rollout with the new Instructions", async () => {
  const runId = "ra000000-0000-4000-8000-00000000000a";
  const rolloutSide = { ...liveSide, position: "second", kind: "rollout", instructions_version_number: 2, score: 1 / 3 };
  const rolledOut = results(twoSided(runId, { kind: "rollout", sides: [liveSide, rolloutSide] }), []);
  setUpPublished({ cases: [leaveCase], runs: [rolledOut] });
  renderStudio(agentPage(hrHelper.id));

  const runs = await screen.findByRole("list", { name: "Evaluation Runs" }, { timeout: 5000 });
  expect(runs).toHaveTextContent("Rollout evaluation");
  expect(runs).toHaveTextContent("Version 1: 67% · Rollout of Version 1: 33%");
  const detail = await screen.findByRole("region", { name: "Run of 2026-11-12 10:00 UTC" });
  expect(detail).toHaveTextContent(
    "Version 1 · Instructions v1 · openai gpt-4.1-mini against Rollout of Version 1 · Instructions v2 · openai gpt-4.1-mini",
  );
});
