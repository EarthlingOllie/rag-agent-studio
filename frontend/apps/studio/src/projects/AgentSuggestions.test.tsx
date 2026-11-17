import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { fakeAgentsApi, hrHelper, oldHelper } from "../test/agents";
import { adaSession, fakeAuthApi } from "../test/auth";
import { failedResult, fakeEvaluationApi, leaveCase, parkingCase, passed, results, run, runCaseId } from "../test/evaluation";
import { fakeProjectsApi, hrProject } from "../test/projects";
import { renderStudio } from "../test/render";
import {
  citingSuggestion,
  deletedCase,
  estimateOf,
  evidenceCount,
  failedCase,
  failedReply,
  fakeSuggestionsApi,
  retrievalSuggestion,
  suggestion,
} from "../test/suggestions";

const organisationId = adaSession.organisations[0]?.id ?? "";
const publishedHelper: typeof hrHelper = { ...hrHelper, live_version: { id: "a1e00000-0000-4000-8000-000000000001", number: 1 } };
const evaluationPage = (agentId: string) => `/organisations/${organisationId}/projects/${hrProject.id}/agents/${agentId}/evaluation`;

function setUp(
  options: Parameters<typeof fakeSuggestionsApi>[0] = {},
  agents = [publishedHelper],
  evaluation: Parameters<typeof fakeEvaluationApi>[0] = {},
) {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeAgentsApi({ agents });
  fakeEvaluationApi(evaluation);
  return fakeSuggestionsApi(options);
}

async function openSuggestions(user = userEvent.setup()) {
  await user.click(await screen.findByRole("radio", { name: "Suggestions" }, { timeout: 5000 }));
  return screen.findByRole("region", { name: "Suggestions" });
}

test("the Evaluation view's Suggestions tab lists runs, and a Suggestion shows its explanation, Diff and evidence", async () => {
  const user = userEvent.setup();
  setUp({ suggestions: [[citingSuggestion]] });
  renderStudio(evaluationPage(publishedHelper.id));

  // The Evaluation Set and Runs come first.
  expect(await screen.findByRole("radio", { name: "Evaluation Set and Runs" }, { timeout: 5000 })).toBeChecked();
  const tab = await openSuggestions(user);

  const runs = await within(tab).findByRole("list", { name: "Suggestion runs" });
  const row = within(runs).getByRole("listitem");
  expect(row).toHaveTextContent("Suggestion of 2026-11-16 09:00 UTC");
  expect(row).toHaveTextContent("Completed");
  expect(row).toHaveTextContent("2026-11-03 to 2026-11-16 (UTC)");
  expect(row).toHaveTextContent("Changes suggested");
  // The newest is shown.
  const detail = await within(tab).findByRole("region", { name: "Suggestion of 2026-11-16 09:00 UTC" });
  expect(within(detail).getByText("Replies made claims without citing the handbook.")).toBeInTheDocument();
  expect(detail).toHaveTextContent("Proposed by openai:gpt-4.1-mini.");
  const changes = within(detail).getByRole("list", { name: "Suggested changes" });
  expect(within(changes).getByRole("heading", { level: 4, name: "System prompt" })).toBeInTheDocument();
  const diff = within(changes).getByRole("table", { name: "Suggested change to the system prompt" });
  expect(within(diff).getByText("Always cite the passage you used.").closest("tr")).toHaveTextContent("Added");
  expect(within(changes).getByText("Replies failed grounding, so ask for citations.")).toBeInTheDocument();
  // Its evidence chip opens the reply in the Agent's Conversations viewer.
  const cited = within(changes).getByRole("list", { name: "Evidence for the system prompt change" });
  const chip = within(cited).getByRole("link", { name: "E1 · 2026-11-14 · Live Verdict failed" });
  expect(chip).toHaveAttribute(
    "href",
    `/organisations/${organisationId}/projects/${hrProject.id}/agents/${publishedHelper.id}/conversations/${failedReply.conversation_id as string}#message-${failedReply.message_id as string}`,
  );
  // All the evidence, purged text said so.
  expect(detail).toHaveTextContent("2 of 3 pieces of evidence in the range");
  const evidence = within(detail).getByRole("list", { name: "Evidence" });
  expect(within(evidence).getAllByRole("link").map((link) => link.textContent)).toEqual([
    "E1 · 2026-11-14 · Live Verdict failed",
    "E2 · 2026-11-03 · Text purged · Live Verdict failed",
  ]);
});

test("a retrieval change and a Knowledge Base gap show with every kind of evidence, cases opening in Run detail", async () => {
  const user = userEvent.setup();
  setUp({ suggestions: [[retrievalSuggestion]] });
  renderStudio(evaluationPage(publishedHelper.id));
  const tab = await openSuggestions(user);

  const detail = await within(tab).findByRole("region", { name: "Suggestion of 2026-11-16 09:00 UTC" });
  const changes = within(detail).getByRole("list", { name: "Suggested changes" });
  expect(within(changes).getByRole("heading", { level: 4, name: "Minimum Score" })).toBeInTheDocument();
  const diff = within(changes).getByRole("table", { name: "Suggested change to the minimum score" });
  expect(within(diff).getByText("0.45").closest("tr")).toHaveTextContent("Added");
  expect(within(diff).getByText("0.5").closest("tr")).toHaveTextContent("Removed");
  // A reply with every reason, and the case result it was checked against.
  const cited = within(changes).getByRole("list", { name: "Evidence for the minimum score change" });
  expect(within(cited).getAllByRole("link").map((link) => link.textContent)).toEqual([
    "E3 · 2026-11-12 · Live Verdict failed · Thumbs-down · Rated 1 or 2",
    "E4 · 2026-11-10 · Evaluation Case failed",
  ]);
  expect(within(cited).getByRole("link", { name: "E4 · 2026-11-10 · Evaluation Case failed" })).toHaveAttribute(
    "href",
    `${evaluationPage(publishedHelper.id)}?run=${failedCase.evaluation_run_id ?? ""}&case=${failedCase.run_case_id ?? ""}`,
  );
  // The gaps, never a change, with the Knowledge Base a link away.
  const gaps = within(detail).getByRole("list", { name: "Knowledge Base gaps" });
  expect(within(gaps).getByRole("heading", { level: 5, name: "Parental leave" })).toBeInTheDocument();
  expect(gaps).toHaveTextContent("Visitors asked about parental leave and no Chunk covered it.");
  expect(within(gaps).getByRole("link", { name: "E5 · 2026-11-10 · Case deleted" })).toBeInTheDocument();
  expect(within(detail).getByRole("link", { name: "Open the Knowledge Base" })).toHaveAttribute(
    "href",
    `/organisations/${organisationId}/projects/${hrProject.id}`,
  );
});

const unjudgedReply: typeof failedReply = {
  ...failedReply,
  id: "5e000000-0000-4000-8000-000000000006",
  label: "E6",
  kind: "thumbs_down",
  kinds: ["thumbs_down"],
  live_verdict: null,
};

test("a Suggestion with only Knowledge Base gaps reads as no configuration change", async () => {
  const user = userEvent.setup();
  const gapsOnly = suggestion("5a000000-0000-4000-8000-000000000005", "completed", {
    outcome: "gaps_only",
    explanation: "The knowledge base lacks parental leave.",
    evidence_total: 1,
    gaps: retrievalSuggestion.gaps,
    evidence: [deletedCase, unjudgedReply],
  });
  setUp({ suggestions: [[gapsOnly]] });
  renderStudio(evaluationPage(publishedHelper.id));
  const tab = await openSuggestions(user);

  const runs = await within(tab).findByRole("list", { name: "Suggestion runs" });
  expect(within(runs).getByRole("listitem")).toHaveTextContent("No configuration change");
  const detail = await within(tab).findByRole("region", { name: "Suggestion of 2026-11-16 09:00 UTC" });
  expect(within(detail).getByText("No configuration change.")).toBeInTheDocument();
  expect(within(detail).queryByRole("list", { name: "Suggested changes" })).not.toBeInTheDocument();
  expect(within(detail).getByRole("list", { name: "Knowledge Base gaps" })).toBeInTheDocument();
  // A reply that was never judged says only why it counts.
  expect(within(detail).getByRole("link", { name: "E6 · 2026-11-14 · Thumbs-down" })).toBeInTheDocument();
});

test("choosing another Suggestion shows it; a failed run says why and a no-change one says so", async () => {
  const user = userEvent.setup();
  const failed = suggestion("5a000000-0000-4000-8000-000000000002", "failed", {
    created_at: "2026-11-15T09:00:00Z",
    error_message: "The Evaluation Model didn't propose a Suggestion in time.",
  });
  const unchanged = suggestion("5a000000-0000-4000-8000-000000000003", "completed", {
    created_at: "2026-11-14T09:00:00Z",
    outcome: "no_change",
    explanation: "Nothing in the configuration would help.",
    evidence_total: 1,
    evidence: [{ ...failedReply, live_verdict: "pass" }],
  });
  setUp({ suggestions: [[failed], [unchanged]] });
  renderStudio(evaluationPage(publishedHelper.id));
  const tab = await openSuggestions(user);

  const failedDetail = await within(tab).findByRole("region", { name: "Suggestion of 2026-11-15 09:00 UTC" });
  expect(within(failedDetail).getByRole("alert")).toHaveTextContent("The Evaluation Model didn't propose a Suggestion in time.");

  await user.click(within(tab).getByRole("button", { name: "Suggestion of 2026-11-14 09:00 UTC" }));

  const detail = await within(tab).findByRole("region", { name: "Suggestion of 2026-11-14 09:00 UTC" });
  expect(within(tab).getByRole("button", { name: "Suggestion of 2026-11-14 09:00 UTC" })).toHaveAttribute("aria-current", "true");
  expect(within(detail).getByText("No change suggested.")).toBeInTheDocument();
  expect(within(detail).getByText("Nothing in the configuration would help.")).toBeInTheDocument();
  expect(within(detail).queryByRole("list", { name: "Suggested changes" })).not.toBeInTheDocument();
  expect(within(detail).getByRole("link", { name: "E1 · 2026-11-14 · Live Verdict passed" })).toBeInTheDocument();
});

test("an Editor suggests changes over the last 14 UTC days, and the Studio polls the run until it completes", async () => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-11-16T12:00:00Z"));
  const user = userEvent.setup();
  const id = citingSuggestion.id;
  const { requests } = setUp({
    started: [suggestion(id, "queued"), suggestion(id, "proposing"), citingSuggestion],
  });
  renderStudio(evaluationPage(publishedHelper.id));
  const tab = await openSuggestions(user);
  expect(await within(tab).findByRole("heading", { level: 3, name: "No Suggestions yet" })).toBeInTheDocument();

  await user.click(within(tab).getByRole("button", { name: "Suggest changes" }));
  const dialog = await screen.findByRole("dialog", { name: "Suggest changes" });
  expect(within(dialog).getByLabelText("From (UTC day)")).toHaveValue("2026-11-03");
  expect(within(dialog).getByLabelText("To (UTC day)")).toHaveValue("2026-11-16");
  await user.click(within(dialog).getByRole("button", { name: "Start Suggestion run" }));

  await waitFor(() => {
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  expect(requests).toEqual([{ range_start: "2026-11-03", range_end: "2026-11-16" }]);
  const detail = await within(tab).findByRole("region", { name: "Suggestion of 2026-11-16 09:00 UTC" });
  // While it runs, its progress shows and no second run can start.
  expect(await within(detail).findByText("Proposing…", {}, { timeout: 5000 })).toBeInTheDocument();
  expect(within(tab).getByRole("button", { name: "Suggesting…" })).toBeDisabled();
  expect(await within(detail).findByText("Replies made claims without citing the handbook.", {}, { timeout: 5000 })).toBeInTheDocument();
  vi.useRealTimers();
});

test("the run dialog takes another range, refuses a backwards one, and shows a refusal's reason", async () => {
  const user = userEvent.setup();
  const { requests } = setUp({ startStatus: 409, startDetail: "This Agent is archived. An Owner can restore it." });
  renderStudio(evaluationPage(publishedHelper.id));
  const tab = await openSuggestions(user);

  await user.click(within(tab).getByRole("button", { name: "Suggest changes" }));
  const dialog = await screen.findByRole("dialog", { name: "Suggest changes" });
  const from = within(dialog).getByLabelText("From (UTC day)");
  const to = within(dialog).getByLabelText("To (UTC day)");
  await user.clear(to);
  await user.type(to, "2026-11-01");
  await user.clear(from);
  await user.type(from, "2026-11-02");

  expect(within(dialog).getByRole("alert")).toHaveTextContent("The range must start on or before the day it ends.");
  expect(within(dialog).getByRole("button", { name: "Start Suggestion run" })).toBeDisabled();

  await user.clear(from);
  await user.type(from, "2026-10-20");
  await user.click(within(dialog).getByRole("button", { name: "Start Suggestion run" }));

  expect(await within(dialog).findByRole("alert")).toHaveTextContent("This Agent is archived. An Owner can restore it.");
  expect(requests).toEqual([{ range_start: "2026-10-20", range_end: "2026-11-01" }]);

  await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
  await waitFor(() => {
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

test("an Agent never Published can't start a run, and an archived Agent's Suggestions are read only", async () => {
  const user = userEvent.setup();
  setUp({ suggestions: [[citingSuggestion]] }, [hrHelper, oldHelper]);
  const view = renderStudio(evaluationPage(hrHelper.id));
  let tab = await openSuggestions(user);

  expect(within(tab).getByRole("button", { name: "Suggest changes" })).toBeDisabled();
  expect(tab).toHaveTextContent("Publish this Agent first: a Suggestion is made from its Live Version's replies.");
  view.unmount();

  renderStudio(evaluationPage(oldHelper.id));
  tab = await openSuggestions(user);
  expect(tab).toHaveTextContent("This Agent is archived: its Suggestions are read only, and it starts no Suggestion run.");
  expect(within(tab).queryByRole("button", { name: "Suggest changes" })).not.toBeInTheDocument();
  expect(await within(tab).findByRole("region", { name: "Suggestion of 2026-11-16 09:00 UTC" })).toBeInTheDocument();
});

test("Suggestions that can't be loaded say so", async () => {
  const user = userEvent.setup();
  setUp({ failList: true });
  const view = renderStudio(evaluationPage(publishedHelper.id));
  let tab = await openSuggestions(user);
  expect(await within(tab).findByRole("heading", { level: 3, name: "The Suggestions could not be loaded" }, { timeout: 5000 })).toBeInTheDocument();
  view.unmount();

  setUp({ suggestions: [[citingSuggestion]], failRead: true });
  renderStudio(evaluationPage(publishedHelper.id));
  tab = await openSuggestions(user);
  expect(await within(tab).findByText("The Suggestion could not be loaded. Try again shortly.", {}, { timeout: 5000 })).toBeInTheDocument();
});

test("a refusal without a reason says to try again", async () => {
  const user = userEvent.setup();
  setUp({ startStatus: 500 });
  renderStudio(evaluationPage(publishedHelper.id));
  const tab = await openSuggestions(user);

  await user.click(within(tab).getByRole("button", { name: "Suggest changes" }));
  const dialog = await screen.findByRole("dialog", { name: "Suggest changes" });
  await user.click(within(dialog).getByRole("button", { name: "Start Suggestion run" }));

  expect(await within(dialog).findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});

test("an Evaluation Case's evidence opens its result in Run detail", async () => {
  const runId = "r1000000-0000-4000-8000-000000000002";
  const checked = results(run(runId, "completed", 2, 2, { created_at: "2026-11-10T11:00:00Z" }), [
    [leaveCase, passed],
    [parkingCase, failedResult],
  ]);
  const newer = results(run("r1000000-0000-4000-8000-000000000003", "completed", 1, 1), [[leaveCase, passed]]);
  setUp({}, [publishedHelper], { cases: [leaveCase, parkingCase], runs: [newer, checked] });

  renderStudio(`${evaluationPage(publishedHelper.id)}?run=${runId}&case=${runCaseId(parkingCase)}`);

  // The Run it names is shown, not the newest, with the case's result marked.
  const detail = await screen.findByRole("region", { name: "Run of 2026-11-10 11:00 UTC" }, { timeout: 5000 });
  const cases = within(detail).getByRole("list", { name: "Cases" });
  const marked = within(cases)
    .getAllByRole("listitem")
    .filter((item) => item.getAttribute("aria-current") === "true");
  expect(marked).toHaveLength(1);
  expect(marked[0]).toHaveTextContent(parkingCase.question);
  expect(screen.getByRole("button", { name: "Run of 2026-11-10 11:00 UTC" })).toHaveAttribute("aria-current", "true");
});

test("the run dialog shows the range's evidence by kind, warns below 10 pieces without blocking, and shows the estimated Cost", async () => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-11-16T12:00:00Z"));
  const user = userEvent.setup();
  const { requests, evidenceReads } = setUp({ started: [citingSuggestion] });
  renderStudio(evaluationPage(publishedHelper.id));
  const tab = await openSuggestions(user);

  await user.click(within(tab).getByRole("button", { name: "Suggest changes" }));
  const dialog = await screen.findByRole("dialog", { name: "Suggest changes" });

  const evidence = await within(dialog).findByRole("status", { name: "Evidence in the range" });
  await waitFor(() => {
    expect(evidence).toHaveTextContent("3 pieces of evidence: 2 failed Live Verdicts, 1 thumbs-down, 1 rated 1 or 2, 0 failed Evaluation Cases");
  });
  expect(within(dialog).getByText("Fewer than 10 pieces of evidence: the Suggestion is likely to be noise. You can still start it.")).toBeInTheDocument();
  const cost = within(dialog).getByRole("status", { name: "Estimated Cost" });
  await waitFor(() => {
    expect(cost).toHaveTextContent("About $0.0073: proposing $0.0028, checking against the Evaluation Set $0.0045");
  });
  expect(evidenceReads).toEqual(["2026-11-03..2026-11-16"]);

  // Another range is counted again.
  const from = within(dialog).getByLabelText("From (UTC day)");
  await user.clear(from);
  await user.type(from, "2026-11-10");
  await waitFor(() => {
    expect(evidenceReads).toContain("2026-11-10..2026-11-16");
  });

  // The warning never blocks starting.
  await user.click(within(dialog).getByRole("button", { name: "Start Suggestion run" }));
  await waitFor(() => {
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  expect(requests).toEqual([{ range_start: "2026-11-10", range_end: "2026-11-16" }]);
  expect(await within(tab).findByRole("region", { name: "Suggestion of 2026-11-16 09:00 UTC" })).toBeInTheDocument();
  vi.useRealTimers();
});

test("with plenty of evidence there is no warning; without an Evaluation Set nothing is checked; unknown prices say so", async () => {
  const user = userEvent.setup();
  const plenty = (range: { range_start: string; range_end: string }) =>
    evidenceCount(range, { total: 64, live_verdict: 60, thumbs_down: 3, low_rating: 1, evaluation_case: 1, likely_noise: false });
  setUp({ evidence: plenty, estimate: (evidence) => estimateOf(evidence, { has_evaluation_set: false, checking_usd: null, total_usd: "0.0028" }) });
  const view = renderStudio(evaluationPage(publishedHelper.id));
  let tab = await openSuggestions(user);

  await user.click(within(tab).getByRole("button", { name: "Suggest changes" }));
  let dialog = await screen.findByRole("dialog", { name: "Suggest changes" });
  await waitFor(() => {
    expect(within(dialog).getByRole("status", { name: "Evidence in the range" })).toHaveTextContent("64 pieces of evidence: 60 failed Live Verdicts, 3 thumbs-down, 1 rated 1 or 2, 1 failed Evaluation Case. A run reads the 50 most recent.");
  });
  expect(within(dialog).queryByText(/likely to be noise/)).not.toBeInTheDocument();
  await waitFor(() => {
    expect(within(dialog).getByRole("status", { name: "Estimated Cost" })).toHaveTextContent("About $0.0028: proposing $0.0028. Not checked: this Agent has no Evaluation Set.");
  });
  view.unmount();

  setUp({ estimate: (evidence) => estimateOf(evidence, { proposing_usd: null, checking_usd: null, total_usd: null }) });
  renderStudio(evaluationPage(publishedHelper.id));
  tab = await openSuggestions(user);
  await user.click(within(tab).getByRole("button", { name: "Suggest changes" }));
  dialog = await screen.findByRole("dialog", { name: "Suggest changes" });
  await waitFor(() => {
    expect(within(dialog).getByRole("status", { name: "Estimated Cost" })).toHaveTextContent("The Cost can't be estimated: a model this run uses has no price set.");
  });
});

test("the dialog's refused reads say why, and a backwards range reads nothing", async () => {
  const user = userEvent.setup();
  const { evidenceReads } = setUp({ refuseReads: true });
  renderStudio(evaluationPage(publishedHelper.id));
  const tab = await openSuggestions(user);

  await user.click(within(tab).getByRole("button", { name: "Suggest changes" }));
  const dialog = await screen.findByRole("dialog", { name: "Suggest changes" });
  await waitFor(() => {
    expect(within(dialog).getByRole("status", { name: "Estimated Cost" })).toHaveTextContent("The Cost could not be estimated. This Agent is archived. An Owner can restore it.");
  });
  expect(within(dialog).getByRole("status", { name: "Evidence in the range" })).toHaveTextContent("The evidence could not be counted. This Agent is archived. An Owner can restore it.");
  const reads = evidenceReads.length;
  const to = within(dialog).getByLabelText("To (UTC day)");
  await user.clear(to);
  await user.type(to, "2020-01-01");
  expect(within(dialog).getByRole("status", { name: "Evidence in the range" })).toHaveTextContent("Choose a range to count its evidence.");
  expect(within(dialog).getByRole("status", { name: "Estimated Cost" })).toHaveTextContent("Choose a range to see the estimated Cost.");
  expect(evidenceReads).toHaveLength(reads);
});

test("a Suggestion shows its estimated and actual Cost, and the list its Cost", async () => {
  const user = userEvent.setup();
  const checked = suggestion("5a000000-0000-4000-8000-000000000007", "completed", {
    outcome: "no_change",
    cost: { estimated_proposing_usd: "0.0028", estimated_checking_usd: "0.00448", proposing_usd: "0.00056" },
  });
  const unpriced = suggestion("5a000000-0000-4000-8000-000000000008", "failed", {
    created_at: "2026-11-15T09:00:00Z",
    cost: { estimated_proposing_usd: null, estimated_checking_usd: null, proposing_usd: null },
  });
  setUp({ suggestions: [[checked], [unpriced]] });
  renderStudio(evaluationPage(publishedHelper.id));
  const tab = await openSuggestions(user);

  const runs = await within(tab).findByRole("list", { name: "Suggestion runs" });
  const [first, second] = within(runs).getAllByRole("listitem");
  expect(first).toHaveTextContent("Cost $0.00056");
  expect(second).toHaveTextContent("Cost unknown");
  let detail = await within(tab).findByRole("region", { name: "Suggestion of 2026-11-16 09:00 UTC" });
  expect(detail).toHaveTextContent("Proposing cost $0.00056 (estimated $0.0028). Checking estimated at $0.0045.");

  await user.click(within(tab).getByRole("button", { name: "Suggestion of 2026-11-15 09:00 UTC" }));
  detail = await within(tab).findByRole("region", { name: "Suggestion of 2026-11-15 09:00 UTC" });
  expect(detail).toHaveTextContent("Proposing cost unknown (no estimate). Not checked.");
});

test("an Editor cancels a run in progress; it stops and keeps what it spent", async () => {
  const user = userEvent.setup();
  const proposing = suggestion("5a000000-0000-4000-8000-000000000009", "proposing", {
    cost: { estimated_proposing_usd: "0.0028", estimated_checking_usd: null, proposing_usd: null },
  });
  const { cancels } = setUp({ suggestions: [[proposing]] });
  renderStudio(evaluationPage(publishedHelper.id));
  const tab = await openSuggestions(user);

  const detail = await within(tab).findByRole("region", { name: "Suggestion of 2026-11-16 09:00 UTC" });
  expect(within(detail).getByText("Proposing…")).toBeInTheDocument();
  await user.click(within(detail).getByRole("button", { name: "Cancel run" }));

  await waitFor(() => {
    expect(within(detail).getByText("Cancelled")).toBeInTheDocument();
  });
  expect(cancels).toEqual([proposing.id]);
  expect(within(detail).queryByRole("button", { name: "Cancel run" })).not.toBeInTheDocument();
  expect(within(detail).getByText("This run was cancelled. It stopped before its next phase and keeps what it spent.")).toBeInTheDocument();
});

test("a cancel refused because the run already finished says why", async () => {
  const user = userEvent.setup();
  setUp({ suggestions: [[suggestion("5a000000-0000-4000-8000-000000000010", "queued")]], cancelStatus: 409 });
  renderStudio(evaluationPage(publishedHelper.id));
  const tab = await openSuggestions(user);

  const detail = await within(tab).findByRole("region", { name: "Suggestion of 2026-11-16 09:00 UTC" });
  await user.click(within(detail).getByRole("button", { name: "Cancel run" }));

  expect(await within(detail).findByRole("alert")).toHaveTextContent("This Suggestion run has already finished.");
});
