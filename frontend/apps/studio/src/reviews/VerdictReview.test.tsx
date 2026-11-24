import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { fakeAgentsApi, hrHelper } from "../test/agents";
import { adaSession, fakeAuthApi } from "../test/auth";
import { VISITOR_CONVERSATION_ID, fakeConversationsApi, judgedVerdict, visitorTrace } from "../test/conversations";
import { failedResult, fakeEvaluationApi, leaveCase, passed, results, run, verdict } from "../test/evaluation";
import { fakeProjectsApi, hrProject } from "../test/projects";
import { renderStudio } from "../test/render";
import { aReview, fakeAgreementApi, fakeVerdictReviewsApi } from "../test/reviews";

const organisationId = adaSession.organisations[0]?.id ?? "";
const projectPage = `/organisations/${organisationId}/projects/${hrProject.id}`;

/** A finished Run of one case whose answer has the given Verdicts. */
function runWith(...verdicts: (typeof passed)["verdicts"]) {
  return results(run("r1000000-0000-4000-8000-000000000001", "completed", 1, 1), [[leaveCase, { ...failedResult, verdicts }]]);
}

/** Opens Run detail on the Run; its answer's Verdicts. */
async function verdictsOf(finished: ReturnType<typeof runWith>) {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeAgentsApi({ agents: [hrHelper] });
  fakeEvaluationApi({ cases: [leaveCase], runs: [finished] });
  fakeAgreementApi({});
  renderStudio(`${projectPage}/agents/${hrHelper.id}/evaluation`);
  const detail = await screen.findByRole("region", { name: "Run of 2026-11-12 10:00 UTC" }, { timeout: 5000 });
  return within(detail).getByRole("list", { name: "Verdicts" });
}

const reviewOf = (scope: HTMLElement, name: string) => within(scope).getByRole("group", { name: `Your review of ${name}` });

// Run detail

test("an Editor agrees with a judged Verdict in Run detail and the review is shown on it", async () => {
  const user = userEvent.setup();
  const reference = verdict("reference_answer", "fail", "The answer doesn't name the north car park.");
  const finished = runWith(reference, verdict("grounding", "fail", "Nothing cited supports it."));
  const { puts } = fakeVerdictReviewsApi({ [reference.id]: reference });
  const verdicts = await verdictsOf(finished);
  const review = reviewOf(verdicts, "the Reference answer Verdict");

  await user.click(within(review).getByRole("button", { name: "Agree" }));

  // Agreeing gives the Evaluation Model's own outcome as the Editor's.
  expect(puts).toEqual([{ target: reference.id, body: { outcome: "fail", reason: null } }]);
  expect(await within(review).findByText("Agreed")).toBeInTheDocument();
  expect(review).toHaveTextContent("by Grace Hopper on 2026-11-20 09:30 UTC");
  expect(review).not.toHaveTextContent("from the Review sample");
  expect(within(review).queryByRole("button", { name: "Agree" })).not.toBeInTheDocument();
  // The Verdict itself is unchanged.
  expect(verdicts.firstElementChild?.firstElementChild).toHaveTextContent("Reference answer: Fail. The answer doesn't name the north car park.");
  expect(within(reviewOf(verdicts, "the Grounding Verdict")).getByRole("button", { name: "Agree" })).toBeInTheDocument();
});

test("disagreeing asks for an optional reason and saves the opposite outcome with it", async () => {
  const user = userEvent.setup();
  const grounding = verdict("grounding", "pass", "Every claim is in the cited excerpt.");
  const { puts } = fakeVerdictReviewsApi({ [grounding.id]: grounding });
  const review = reviewOf(await verdictsOf(runWith(grounding)), "the Grounding Verdict");

  await user.click(within(review).getByRole("button", { name: "Disagree" }));
  const form = within(review).getByRole("form", { name: "Why you disagree" });
  const reason = within(form).getByRole("textbox", { name: "Why you disagree (optional)" });
  expect(reason).toHaveAttribute("maxLength", "1000");
  expect(reason).toHaveAccessibleDescription("Up to 1000 characters. It helps improve how Verdicts are judged.");
  await user.type(reason, "  The 25 days aren't in the excerpt.  ");
  await user.click(within(form).getByRole("button", { name: "Save disagreement" }));

  expect(puts).toEqual([{ target: grounding.id, body: { outcome: "fail", reason: "The 25 days aren't in the excerpt." } }]);
  expect(await within(review).findByText("Disagreed")).toBeInTheDocument();
  expect(review).toHaveTextContent("The 25 days aren't in the excerpt.");
  expect(within(review).queryByRole("form")).not.toBeInTheDocument();
});

test("a disagreement without a reason saves none, and Cancel leaves the Verdict unreviewed", async () => {
  const user = userEvent.setup();
  const grounding = verdict("grounding", "fail", "Nothing cited supports it.");
  const { puts } = fakeVerdictReviewsApi({ [grounding.id]: grounding });
  const review = reviewOf(await verdictsOf(runWith(grounding)), "the Grounding Verdict");

  await user.click(within(review).getByRole("button", { name: "Disagree" }));
  await user.click(within(review).getByRole("button", { name: "Cancel" }));
  expect(puts).toEqual([]);
  await user.click(within(review).getByRole("button", { name: "Disagree" }));
  await user.click(within(review).getByRole("button", { name: "Save disagreement" }));

  expect(puts).toEqual([{ target: grounding.id, body: { outcome: "pass", reason: null } }]);
  expect(await within(review).findByText("Disagreed")).toBeInTheDocument();
});

test("a sample review is shown with who gave it and that it came from the Review sample, and can be replaced", async () => {
  const user = userEvent.setup();
  const reference = {
    ...verdict("reference_answer", "pass", "The answer gives the 25 days."),
    review: aReview({ outcome: "fail", reason: "It never says a year.", reviewed_by: "Ada Lovelace", from_sample: true }),
  };
  const { puts } = fakeVerdictReviewsApi({ [reference.id]: reference });
  const review = reviewOf(await verdictsOf(runWith(reference)), "the Reference answer Verdict");
  expect(review).toHaveTextContent("Disagreed");
  expect(review).toHaveTextContent("by Ada Lovelace on 2026-11-20 09:30 UTC, from the Review sample");
  expect(review).toHaveTextContent("It never says a year.");

  await user.click(within(review).getByRole("button", { name: "Change review" }));
  await user.click(within(review).getByRole("button", { name: "Cancel" }));
  expect(review).toHaveTextContent("from the Review sample");
  await user.click(within(review).getByRole("button", { name: "Change review" }));
  await user.click(within(review).getByRole("button", { name: "Agree" }));

  expect(puts).toEqual([{ target: reference.id, body: { outcome: "pass", reason: null } }]);
  expect(await within(review).findByText("Agreed")).toBeInTheDocument();
  // Replaced here, it no longer came from the Review sample.
  expect(review).not.toHaveTextContent("from the Review sample");
});

test("removing a review leaves the Verdict unreviewed again", async () => {
  const user = userEvent.setup();
  const grounding = { ...verdict("grounding", "fail", "Nothing cited supports it."), review: aReview({ reviewed_by: null }) };
  const { deletes } = fakeVerdictReviewsApi({ [grounding.id]: grounding });
  const review = reviewOf(await verdictsOf(runWith(grounding)), "the Grounding Verdict");
  // Its reviewer has since left.
  expect(review).toHaveTextContent("Agreed");
  expect(review).toHaveTextContent("by a former Member");

  await user.click(within(review).getByRole("button", { name: "Remove review" }));

  expect(deletes).toEqual([grounding.id]);
  expect(await within(review).findByRole("button", { name: "Agree" })).toBeInTheDocument();
  expect(review).not.toHaveTextContent("Agreed");
});

test("a review that can't be saved says why", async () => {
  const user = userEvent.setup();
  const grounding = verdict("grounding", "fail", "Nothing cited supports it.");
  fakeVerdictReviewsApi({ [grounding.id]: grounding }, { status: 404 });
  const review = reviewOf(await verdictsOf(runWith(grounding)), "the Grounding Verdict");

  await user.click(within(review).getByRole("button", { name: "Agree" }));

  expect(await within(review).findByRole("alert")).toHaveTextContent("This can no longer be reviewed");
});

test("a removal that fails for another reason asks to try again", async () => {
  const user = userEvent.setup();
  const grounding = { ...verdict("grounding", "fail", "Nothing cited supports it."), review: aReview() };
  fakeVerdictReviewsApi({ [grounding.id]: grounding }, { status: 500 });
  const review = reviewOf(await verdictsOf(runWith(grounding)), "the Grounding Verdict");

  await user.click(within(review).getByRole("button", { name: "Remove review" }));

  expect(await within(review).findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
  expect(review).toHaveTextContent("Agreed");
});

test("Expected source, Expect Fallback Text and Stale Verdicts have nothing to review", async () => {
  const verdicts = await verdictsOf(
    runWith(
      verdict("expected_source", "pass", "The answer cited the passage of leave.txt."),
      verdict("fallback", "fail", "The answer wasn't the Fallback Text."),
      verdict("reference_answer", "stale", "Skipped."),
    ),
  );

  expect(within(verdicts).queryByRole("group")).not.toBeInTheDocument();
  expect(within(verdicts).queryByRole("button", { name: "Agree" })).not.toBeInTheDocument();
});

// The Trace

async function liveVerdictOf(liveVerdict: typeof judgedVerdict) {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeAgentsApi({ agents: [hrHelper] });
  fakeConversationsApi({ traces: [{ ...visitorTrace, live_verdict: liveVerdict }] });
  fakeAgreementApi({});
  renderStudio(`${projectPage}/conversations/${VISITOR_CONVERSATION_ID}`);
  const items = within(await screen.findByRole("list", { name: "Messages" }, { timeout: 5000 })).getAllByRole("listitem");
  const trace = within(items[1] as HTMLElement).getByRole("group", { name: "Trace" });
  await userEvent.click(within(trace).getByText("Trace"));
  return within(trace).findByRole("region", { name: "Live Verdict" });
}

test("an Editor reviews each check of a Live Verdict in the Trace", async () => {
  const user = userEvent.setup();
  const liveVerdict = structuredClone(judgedVerdict);
  const grounded = liveVerdict.grounded as NonNullable<typeof liveVerdict.grounded>;
  const answers = liveVerdict.answers_question as NonNullable<typeof liveVerdict.answers_question>;
  const { puts, deletes } = fakeVerdictReviewsApi({
    [`${liveVerdict.id}:grounding`]: grounded,
    [`${liveVerdict.id}:answers_question`]: answers,
  });
  const section = await liveVerdictOf(liveVerdict);

  await user.click(within(reviewOf(section, "the Grounded check")).getByRole("button", { name: "Agree" }));
  const answering = reviewOf(section, "the Answers the question check");
  await user.click(within(answering).getByRole("button", { name: "Disagree" }));
  await user.type(within(answering).getByRole("textbox"), "It does say how to book it.");
  await user.click(within(answering).getByRole("button", { name: "Save disagreement" }));

  expect(puts).toEqual([
    { target: `${liveVerdict.id}:grounding`, body: { outcome: "pass", reason: null } },
    { target: `${liveVerdict.id}:answers_question`, body: { outcome: "pass", reason: "It does say how to book it." } },
  ]);
  expect(await within(answering).findByText("Disagreed")).toBeInTheDocument();
  expect(answering).toHaveTextContent("It does say how to book it.");
  await waitFor(() => {
    expect(reviewOf(section, "the Grounded check")).toHaveTextContent("Agreed");
  });
  await user.click(within(answering).getByRole("button", { name: "Remove review" }));
  expect(deletes).toEqual([`${liveVerdict.id}:answers_question`]);
  expect(await within(answering).findByRole("button", { name: "Disagree" })).toBeInTheDocument();
});

test("after the Purge a Live Verdict's review shows Text purged and can only be removed", async () => {
  const purged = {
    ...judgedVerdict,
    grounded: {
      outcome: "pass" as const,
      reason: null,
      review: aReview({ reason: null, from_sample: true, purged_at: "2026-11-14T10:00:00Z" }),
    },
    answers_question: { outcome: "fail" as const, reason: null, review: null },
    purged_at: "2026-11-14T10:00:00Z",
  };
  fakeVerdictReviewsApi({});
  const section = await liveVerdictOf(purged);

  const grounded = reviewOf(section, "the Grounded check");
  expect(grounded).toHaveTextContent("Disagreed");
  expect(grounded).toHaveTextContent("from the Review sample");
  expect(within(grounded).getByText("Text purged")).toBeInTheDocument();
  expect(within(grounded).queryByRole("button", { name: "Change review" })).not.toBeInTheDocument();
  expect(within(grounded).getByRole("button", { name: "Remove review" })).toBeInTheDocument();
  // Its text is gone, so the unreviewed check can't be reviewed.
  expect(within(reviewOf(section, "the Answers the question check")).queryByRole("button")).not.toBeInTheDocument();
});
