import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { fakeAgentsApi, hrHelper } from "../test/agents";
import { adaSession, fakeAuthApi } from "../test/auth";
import {
  draftSide,
  fakeEvaluationApi,
  liveSide,
  publishSummary,
  results,
  run,
} from "../test/evaluation";
import {
  fakeProjectsApi,
  hrProject,
  instructionsVersion,
} from "../test/projects";
import { renderStudio } from "../test/render";
import { server } from "../test/server";
import type { EvaluationRunSide } from "./evaluation";

const organisationId = adaSession.organisations[0]?.id ?? "";
const agentPage = `/organisations/${organisationId}/projects/${hrProject.id}/agents/${hrHelper.id}`;

const v1 = instructionsVersion(1);
const v2 = instructionsVersion(2, { previous_version_id: v1.id });
const liveHelper = {
  ...hrHelper,
  live_version: { id: "a1e00000-0000-4000-8000-000000000001", number: 1 },
};

/** A finished Run of Version 1 against the Draft, answering with Instructions v2. */
const liveAgainstDraft = run(
  "r1000000-0000-4000-8000-000000000001",
  "completed",
  6,
  6,
  {
    sides: [
      { ...liveSide, cases_passed: 3, cases_failed: 0, score: 1 },
      {
        ...draftSide,
        instructions_draft: false,
        instructions_version_number: 2,
        cases_passed: 2,
        cases_failed: 1,
        score: 2 / 3,
      },
    ],
  },
);

const brokenCase = {
  case_id: "e1000000-0000-4000-8000-000000000002",
  question: "Where do visitors park?",
  reasons: [
    {
      kind: "reference_answer",
      reason: "The answer doesn't name the north car park.",
    },
    { kind: "grounding", reason: "Nothing cited supports it." },
  ],
};

function setUp(
  evaluation: Parameters<typeof fakeEvaluationApi>[0] = {},
  agent: typeof hrHelper = liveHelper,
) {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi({
    versions: {
      [hrProject.id]: { current_version_id: v2.id, versions: [v2, v1] },
    },
  });
  const agents = fakeAgentsApi({
    agents: [agent],
    currentInstructions: { id: v2.id, number: 2 },
  });
  return { agents, evaluation: fakeEvaluationApi(evaluation) };
}

/** Opens the Publish dialog from the top bar and returns its Evaluation section. */
async function evaluationSection() {
  await userEvent.click(
    await within(
      await screen.findByRole("banner", {}, { timeout: 5000 }),
    ).findByRole("button", { name: "Publish" }, { timeout: 5000 }),
  );
  const form = await screen.findByRole("form", { name: "Publish" });
  return {
    form,
    section: within(form).getByRole("region", { name: "Evaluation" }),
  };
}

/** Publishes from the dialog with a note, which works whatever the Evaluation section says. */
async function publishesAnyway(form: HTMLElement) {
  const publish = within(form).getByRole("button", { name: "Publish" });
  expect(publish).toBeEnabled();
  await userEvent.type(within(form).getByLabelText("Note"), "Ship it");
  await userEvent.click(publish);
  expect(
    await within(form).findByText(
      /^Published v2 with Instructions v2\. It is now Live\.$/,
    ),
  ).toBeInTheDocument();
}

test("Regressions are listed with their Verdicts' reasons, and Publishing goes ahead anyway", async () => {
  const { evaluation } = setUp({
    summaries: [
      publishSummary("regressions", {
        run: liveAgainstDraft,
        regressions: [brokenCase],
        lower_score: true,
      }),
    ],
  });
  renderStudio(agentPage);
  const { form, section } = await evaluationSection();

  const warning = await within(section).findByText(/1 Regression/);
  expect(warning).toHaveTextContent(
    "This Draft has 1 Regression: a case that passes on the Live Version fails on the Draft. Its Evaluation score is lower: 67% against 100% on the Live Version.",
  );
  const listed = within(section).getByRole("list", { name: "Regressions" });
  const [item] = within(listed).getAllByRole("listitem") as [HTMLElement];
  expect(item).toHaveTextContent("Where do visitors park?");
  expect(item).toHaveTextContent(
    "Reference answer: The answer doesn't name the north car park.",
  );
  expect(item).toHaveTextContent("Grounding: Nothing cited supports it.");
  expect(evaluation.requests.filter((r) => r.route === "summary")).toEqual([
    { route: "summary", body: { instructions_version_id: null } },
  ]);

  await publishesAnyway(form);
});

test("a lower Evaluation score warns even without a Regression", async () => {
  setUp({
    summaries: [
      publishSummary("regressions", {
        run: liveAgainstDraft,
        lower_score: true,
      }),
    ],
  });
  renderStudio(agentPage);
  const { section } = await evaluationSection();

  expect(
    await within(section).findByText(/Evaluation score is lower/),
  ).toHaveTextContent(
    "Its Evaluation score is lower: 67% against 100% on the Live Version.",
  );
  expect(
    within(section).queryByRole("list", { name: "Regressions" }),
  ).not.toBeInTheDocument();
});

test("several Regressions are counted", async () => {
  const other = {
    ...brokenCase,
    case_id: null,
    question: "How much leave?",
    reasons: [{ kind: "fallback", reason: null }],
  };
  setUp({
    summaries: [
      publishSummary("regressions", {
        run: liveAgainstDraft,
        regressions: [brokenCase, other],
      }),
    ],
  });
  renderStudio(agentPage);
  const { section } = await evaluationSection();

  expect(await within(section).findByText(/2 Regressions/)).toHaveTextContent(
    "This Draft has 2 Regressions: cases that pass on the Live Version fail on the Draft.",
  );
  expect(within(section).getAllByRole("listitem")[1]).toHaveTextContent(
    "How much leave?Expect Fallback Text: failed",
  );
});

test("a clear Run says so with both scores", async () => {
  const clear = {
    ...liveAgainstDraft,
    sides: liveAgainstDraft.sides.map((side) => ({ ...side, score: 1 })),
  };
  setUp({ summaries: [publishSummary("clear", { run: clear })] });
  renderStudio(agentPage);
  const { form, section } = await evaluationSection();

  expect(await within(section).findByText(/No Regressions/)).toHaveTextContent(
    "No Regressions against the Live Version: Evaluation score 100% against 100%.",
  );
  await publishesAnyway(form);
});

test("a Run judged under an earlier Judging setup brings a notice that never blocks", async () => {
  setUp({ summaries: [publishSummary("regressions", { run: liveAgainstDraft, regressions: [brokenCase], earlier_judging_setup: true })] });
  renderStudio(agentPage);
  const { form, section } = await evaluationSection();

  expect(await within(section).findByText(/earlier Judging setup/)).toHaveTextContent(
    "The Draft's latest Run was judged under an earlier Judging setup (another Evaluation Model or Judging guidance version), so its scores may read differently now. You can still Publish.",
  );
  // Beside the summary's own state, which it doesn't replace.
  expect(within(section).getByText(/This Draft has 1 Regression/)).toBeInTheDocument();
  await publishesAnyway(form);
});

test("a Run under the current Judging setup brings no such notice", async () => {
  setUp({ summaries: [publishSummary("clear", { run: liveAgainstDraft })] });
  renderStudio(agentPage);
  const { section } = await evaluationSection();

  await within(section).findByText(/No Regressions/);
  expect(within(section).queryByText(/earlier Judging setup/)).not.toBeInTheDocument();
});

test("a clear Run of the Draft alone gives its score", async () => {
  const alone = run("r1000000-0000-4000-8000-000000000002", "completed", 2, 2);
  setUp({ summaries: [publishSummary("clear", { run: alone })] }, hrHelper);
  renderStudio(agentPage);
  const { section } = await evaluationSection();

  expect(await within(section).findByText(/Evaluated/)).toHaveTextContent(
    "Evaluated: the Draft's Evaluation score is 50%.",
  );
});

test("a Draft alone whose every case was an Error has no score", async () => {
  const errored = run(
    "r1000000-0000-4000-8000-000000000006",
    "completed",
    2,
    2,
  );
  const [side] = errored.sides as [EvaluationRunSide];
  setUp(
    {
      summaries: [
        publishSummary("clear", {
          run: { ...errored, sides: [{ ...side, score: null }] },
        }),
      ],
    },
    hrHelper,
  );
  renderStudio(agentPage);
  const { section } = await evaluationSection();

  expect(await within(section).findByText(/Evaluated/)).toHaveTextContent(
    "Evaluated: the Draft's Evaluation score is none, every case was an Error.",
  );
});

test.each<[...Parameters<typeof publishSummary>, typeof hrHelper, string]>([
  [
    "no_run",
    {},
    liveHelper,
    "The Draft hasn't been evaluated against the Live Version (v1) yet.",
  ],
  ["no_run", {}, hrHelper, "The Draft hasn't been evaluated yet."],
  [
    "live_changed",
    { evaluated_live_version_number: 1 },
    {
      ...liveHelper,
      live_version: { id: "a1e00000-0000-4000-8000-000000000002", number: 2 },
    },
    "The Live Version has changed since the Draft was evaluated: it was compared with v1, and v2 is Live now.",
  ],
  [
    "stale",
    { run: liveAgainstDraft },
    liveHelper,
    "The Draft has changed since it was evaluated: the latest Run describes an earlier Draft revision.",
  ],
  [
    "instructions_differ",
    { run: liveAgainstDraft, publishing_instructions_version_number: 1 },
    liveHelper,
    "Evaluated with Instructions v2, publishing with v1.",
  ],
  [
    "instructions_differ",
    {
      run: { ...liveAgainstDraft, sides: [liveSide, draftSide] },
      publishing_instructions_version_number: null,
    },
    liveHelper,
    "Evaluated with the Instructions Draft, publishing with no Project Instructions.",
  ],
  [
    "instructions_differ",
    {
      run: {
        ...liveAgainstDraft,
        sides: [liveSide, { ...draftSide, instructions_draft: false }],
      },
    },
    liveHelper,
    "Evaluated with no Project Instructions, publishing with v2.",
  ],
])(
  "the %s notice says what the evidence is missing",
  async (state, overrides, agent, notice) => {
    setUp({ summaries: [publishSummary(state, overrides)] }, agent);
    renderStudio(agentPage);
    const { form, section } = await evaluationSection();

    expect(await within(section).findByRole("status")).toHaveTextContent(
      notice,
    );
    expect(within(form).getByRole("button", { name: "Publish" })).toBeEnabled();
  },
);

test("an Agent without an Evaluation Set gets a one-line hint and no Evaluate action", async () => {
  setUp();
  renderStudio(agentPage);
  const { form, section } = await evaluationSection();

  expect(
    await within(section).findByText(/No Evaluation Set yet/),
  ).toHaveTextContent(
    "No Evaluation Set yet. Add the questions that matter on the Evaluation tab to check a Draft before Publishing.",
  );
  expect(
    within(section).getByRole("link", { name: "Evaluation tab" }),
  ).toHaveAttribute("href", `${agentPage}/evaluation`);
  expect(
    within(section).queryByRole("button", { name: "Evaluate" }),
  ).not.toBeInTheDocument();
  await publishesAnyway(form);
});

test("the summary follows the Instructions chosen in the dialog", async () => {
  const { evaluation } = setUp({ summaries: [publishSummary("no_run")] });
  renderStudio(agentPage);
  const { form } = await evaluationSection();
  await within(form).findByRole("option", { name: "v1 · Note 1" });

  await userEvent.selectOptions(
    within(form).getByRole("combobox", { name: "Project Instructions" }),
    "v1 · Note 1",
  );

  await vi.waitFor(() => {
    expect(
      evaluation.requests.filter((r) => r.route === "summary").at(-1),
    ).toEqual({
      route: "summary",
      body: { instructions_version_id: v1.id },
    });
  });
});

test("Evaluate starts a Live-against-Draft Run with the dialog's Instructions, shows its progress, then the new summary", async () => {
  const runId = "r1000000-0000-4000-8000-000000000003";
  const started = [
    results(run(runId, "queued", 0, 6, { sides: liveAgainstDraft.sides }), []),
    results(run(runId, "running", 3, 6, { sides: liveAgainstDraft.sides }), []),
    results({ ...liveAgainstDraft, id: runId }, []),
  ];
  const { evaluation } = setUp({
    started,
    summaries: [
      publishSummary("no_run"),
      publishSummary("no_run"),
      publishSummary("regressions", {
        run: liveAgainstDraft,
        regressions: [brokenCase],
      }),
    ],
  });
  renderStudio(agentPage);
  const { form, section } = await evaluationSection();
  await within(form).findByRole("option", { name: "v1 · Note 1" });
  await userEvent.selectOptions(
    within(form).getByRole("combobox", { name: "Project Instructions" }),
    "v1 · Note 1",
  );
  await within(section).findByRole("status");

  await userEvent.click(
    within(section).getByRole("button", { name: "Evaluate" }),
  );

  expect(evaluation.requests.filter((r) => r.route === "start")).toEqual([
    {
      route: "start",
      body: { instructions_draft: false, instructions_version_id: v1.id },
    },
  ]);
  expect(
    await within(section).findByRole(
      "meter",
      { name: "Answers given" },
      { timeout: 5000 },
    ),
  ).toBeInTheDocument();
  expect(
    within(section).getByRole("button", { name: "Evaluating…" }),
  ).toBeDisabled();
  expect(within(form).getByRole("button", { name: "Publish" })).toBeEnabled();
  expect(
    await within(section).findByText(/1 Regression/, {}, { timeout: 8000 }),
  ).toBeInTheDocument();
  expect(within(section).queryByRole("meter")).not.toBeInTheDocument();
  expect(
    within(section).getByRole("button", { name: "Evaluate" }),
  ).toBeEnabled();
});

test("Evaluate is disabled while a Run started elsewhere, such as the Evaluation view, is in progress", async () => {
  setUp({
    runs: [
      results(
        run("r1000000-0000-4000-8000-000000000008", "running", 2, 6, {
          sides: liveAgainstDraft.sides,
        }),
        [],
      ),
    ],
    summaries: [publishSummary("no_run")],
  });
  renderStudio(agentPage);
  const { form, section } = await evaluationSection();
  await within(section).findByRole("status");

  expect(
    await within(section).findByRole("button", { name: "Evaluating…" }),
  ).toBeDisabled();
  expect(
    within(section).queryByRole("button", { name: "Evaluate" }),
  ).not.toBeInTheDocument();
  expect(within(form).getByRole("button", { name: "Publish" })).toBeEnabled();
});

test("Evaluate with the Current Instructions chooses no Instructions Version", async () => {
  const runId = "r1000000-0000-4000-8000-000000000004";
  const { evaluation } = setUp({
    started: [results({ ...liveAgainstDraft, id: runId }, [])],
    summaries: [publishSummary("no_run")],
  });
  renderStudio(agentPage);
  const { section } = await evaluationSection();
  await within(section).findByRole("status");

  await userEvent.click(
    within(section).getByRole("button", { name: "Evaluate" }),
  );

  await vi.waitFor(() => {
    expect(evaluation.requests.filter((r) => r.route === "start")).toEqual([
      { route: "start", body: { instructions_draft: false } },
    ]);
  });
});

test.each([
  [
    "failed",
    { error_message: "Every case errored: the provider is down." },
    "Every case errored: the provider is down.",
  ],
  ["cancelled", {}, "The Run was cancelled before it finished."],
] as const)(
  "a Run that ends %s says so",
  async (status, overrides, message) => {
    const runId = "r1000000-0000-4000-8000-000000000005";
    setUp({
      started: [results(run(runId, status, 2, 6, overrides), [])],
      summaries: [publishSummary("no_run")],
    });
    renderStudio(agentPage);
    const { section } = await evaluationSection();
    await within(section).findByRole("status");

    await userEvent.click(
      within(section).getByRole("button", { name: "Evaluate" }),
    );

    expect(
      await within(section).findByText(message, {}, { timeout: 5000 }),
    ).toBeInTheDocument();
  },
);

test("a Run whose progress can't be read says so", async () => {
  const runId = "r1000000-0000-4000-8000-000000000007";
  setUp({
    started: [results(run(runId, "queued", 0, 6), [])],
    summaries: [publishSummary("no_run")],
  });
  server.use(
    http.get(
      "*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/evaluation/runs/:runId",
      () => HttpResponse.json({ detail: "Down" }, { status: 500 }),
    ),
  );
  renderStudio(agentPage);
  const { section } = await evaluationSection();
  await within(section).findByRole("status");

  await userEvent.click(
    within(section).getByRole("button", { name: "Evaluate" }),
  );

  expect(
    await within(section).findByText(
      "The Run's progress could not be loaded.",
      {},
      { timeout: 5000 },
    ),
  ).toBeInTheDocument();
});

test("a refused Evaluate says why", async () => {
  setUp({
    startStatus: 409,
    startDetail: "This Agent already has an Evaluation Run in progress.",
    summaries: [publishSummary("no_run")],
  });
  renderStudio(agentPage);
  const { section } = await evaluationSection();
  await within(section).findByRole("status");

  await userEvent.click(
    within(section).getByRole("button", { name: "Evaluate" }),
  );

  expect(await within(section).findByRole("alert")).toHaveTextContent(
    "This Agent already has an Evaluation Run in progress.",
  );
});

test("a summary that can't be loaded still lets the Editor publish", async () => {
  setUp({ summaries: { status: 500 } });
  renderStudio(agentPage);
  const { form, section } = await evaluationSection();

  expect(
    await within(section).findByText(
      "The evaluation summary could not be loaded.",
    ),
  ).toBeInTheDocument();
  await publishesAnyway(form);
});
