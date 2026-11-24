import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi, type Session } from "../test/auth";
import { fakeModelsApi } from "../test/models";
import { renderStudio } from "../test/render";
import { fakeReviewSampleApi, leaveGrounding, leaveReference } from "../test/reviews";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const samplePage = `/organisations/${organisationId}/review-sample`;
const editorSession: Session = {
  ...adaSession,
  organisations: adaSession.organisations.map((organisation) => ({ ...organisation, role: "editor" as const })),
};

function open(session: Session = editorSession) {
  fakeAuthApi({ signedInAs: session });
  renderStudio(samplePage);
}

async function item() {
  return within(await screen.findByRole("article", { name: "Item to review" }));
}

test("an Editor is shown an item blind: the question, Reference answer, answer and excerpts, but not the Evaluation Model's verdict", async () => {
  fakeReviewSampleApi({ reviewed: 4 });
  open();

  const shown = await item();

  expect(screen.getByRole("heading", { level: 1, name: "Review sample" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Review sample", current: "page" })).toBeInTheDocument();
  expect(shown.getByRole("heading", { name: "Does the answer agree in meaning with the Reference answer?" })).toBeInTheDocument();
  expect(shown.getByText("HR helper · Evaluation Run")).toBeInTheDocument();
  expect(shown.getByText(leaveReference.item.question)).toBeInTheDocument();
  expect(shown.getByText(leaveReference.item.reference_answer as string)).toBeInTheDocument();
  expect(shown.getByText(leaveReference.item.answer)).toBeInTheDocument();
  const excerpts = shown.getAllByRole("listitem");
  expect(excerpts.map((excerpt) => excerpt.textContent)).toEqual([
    "C1leave.txtCitedEveryone gets 25 days of annual leave a year.",
    "C2sick.txtSick days are paid in full.",
  ]);
  expect(screen.getByText("4 sample reviews so far, 0 of them yours.")).toBeInTheDocument();
  // Blind: nothing of the Evaluation Model's verdict is on the page.
  expect(screen.queryByText(leaveReference.reason)).not.toBeInTheDocument();
  expect(screen.queryByText("Pass", { selector: "span" })).not.toBeInTheDocument();
  const verdict = within(screen.getByRole("group", { name: "Your verdict" }));
  expect(verdict.getAllByRole("button").map((button) => button.textContent)).toEqual(["Pass", "Fail", "Skip"]);
});

test("after agreeing, the Evaluation Model's pass and reason are revealed without a reason field, and Next serves the next item", async () => {
  const api = fakeReviewSampleApi();
  open();
  await item();

  await userEvent.click(screen.getByRole("button", { name: "Pass" }));

  const reveal = within(await screen.findByRole("region", { name: "You agreed with the Evaluation Model" }));
  expect(reveal.getByText(leaveReference.reason)).toBeInTheDocument();
  expect(reveal.getAllByText("Pass")).toHaveLength(2);
  expect(screen.queryByRole("form", { name: "Why you differ" })).not.toBeInTheDocument();
  expect(api.reviews).toEqual([{ verdict_id: leaveReference.item.verdict_id, outcome: "pass" }]);

  await userEvent.click(reveal.getByRole("button", { name: "Next" }));

  const next = await item();
  expect(next.getByRole("heading", { name: "Is every claim in the answer supported by the excerpts it cited?" })).toBeInTheDocument();
  expect(next.queryByText("Reference answer")).not.toBeInTheDocument();
  expect(next.getByText("None: the answer cited nothing.")).toBeInTheDocument();
  expect(screen.getByText("1 sample reviews so far, 1 of them yours.")).toBeInTheDocument();
});

test("after differing, the Editor may save a reason, which is sent with their verdict", async () => {
  const api = fakeReviewSampleApi({ items: [leaveGrounding] });
  open();
  await item();

  await userEvent.click(screen.getByRole("button", { name: "Pass" }));

  const reveal = within(await screen.findByRole("region", { name: "You differed from the Evaluation Model" }));
  expect(reveal.getByText(leaveGrounding.reason)).toBeInTheDocument();
  const form = within(reveal.getByRole("form", { name: "Why you differ" }));
  const save = form.getByRole("button", { name: "Save reason" });
  expect(save).toBeDisabled();
  const reason = form.getByRole("textbox", { name: "Why you differ (optional)" });
  expect(reason).toHaveAttribute("maxlength", "1000");
  expect(reason).toHaveAccessibleDescription("Up to 1000 characters. It helps improve how Verdicts are judged.");

  await userEvent.type(reason, "  It needs no citation for a greeting.  ");
  await userEvent.click(save);

  expect(await screen.findByText("Your reason is saved.")).toBeInTheDocument();
  expect(api.reviews).toEqual([
    { verdict_id: leaveGrounding.item.verdict_id, outcome: "pass" },
    { verdict_id: leaveGrounding.item.verdict_id, outcome: "pass", reason: "It needs no citation for a greeting." },
  ]);
});

test("once the last item is reviewed, Next shows that nothing is left", async () => {
  fakeReviewSampleApi({ items: [leaveGrounding] });
  open();
  await item();
  await userEvent.click(screen.getByRole("button", { name: "Fail" }));
  const reveal = within(await screen.findByRole("region", { name: "You agreed with the Evaluation Model" }));
  expect(reveal.getAllByText("Fail")).toHaveLength(2);
  await userEvent.click(reveal.getByRole("button", { name: "Next" }));

  // The only item was reviewed: nothing is left.
  expect(await screen.findByRole("heading", { name: "Nothing to review" })).toBeInTheDocument();
});

test("a verdict that fails to save says so and keeps the item", async () => {
  fakeReviewSampleApi();
  server.use(
    http.post("*/api/organisations/:organisationId/review-sample/reviews", async () => {
      await delay(50);
      return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    }),
  );
  open();
  await item();

  await userEvent.click(screen.getByRole("button", { name: "Fail" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
  expect(screen.getByRole("article", { name: "Item to review" })).toBeInTheDocument();
});

test("saving a reason can fail", async () => {
  fakeReviewSampleApi({ items: [leaveGrounding] });
  open();
  await item();
  await userEvent.click(screen.getByRole("button", { name: "Pass" }));
  const reveal = within(await screen.findByRole("region", { name: "You differed from the Evaluation Model" }));
  server.use(
    http.post("*/api/organisations/:organisationId/review-sample/reviews", async () => {
      await delay(50);
      return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    }),
  );

  await userEvent.type(reveal.getByRole("textbox"), "Wrong.");
  await userEvent.click(reveal.getByRole("button", { name: "Save reason" }));

  expect(reveal.getByRole("button", { name: "Saving…" })).toBeDisabled();
  expect(await reveal.findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});

test("Skip stores nothing and draws again", async () => {
  const api = fakeReviewSampleApi();
  open(adaSession);
  await item();
  expect(api.draws.count).toBe(1);

  await userEvent.click(screen.getByRole("button", { name: "Skip" }));

  await item();
  expect(api.draws.count).toBe(2);
  expect(api.reviews).toEqual([]);
});

test("an empty sample says there is nothing to review and links back to Models settings", async () => {
  fakeReviewSampleApi({ items: [], reviewed: 12 });
  fakeModelsApi();
  open();

  const empty = await screen.findByRole("heading", { name: "Nothing to review" });

  expect(empty.parentElement).toHaveTextContent("Every judged Verdict by the current Evaluation Model has been reviewed.");
  expect(screen.getByText("12 sample reviews so far, 0 of them yours.")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("link", { name: "Back to Models settings" }));
  expect(await screen.findByRole("heading", { name: "Default Model" })).toBeInTheDocument();
});

test("a sample that can't be loaded says so", async () => {
  server.use(
    http.get("*/api/organisations/:organisationId/review-sample/next", () => HttpResponse.json({ detail: "Down" }, { status: 503 })),
  );
  open();

  expect(await screen.findByRole("alert")).toHaveTextContent("The Review sample could not be loaded");
});
