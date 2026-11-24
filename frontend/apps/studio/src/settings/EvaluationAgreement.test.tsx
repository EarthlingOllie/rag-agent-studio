import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi } from "../test/auth";
import { fakeModelsApi } from "../test/models";
import { renderStudio } from "../test/render";
import { claudeAgreement, fakeAgreementApi, fakeReviewSampleApi, gptAgreement, leaveReference, unreviewed } from "../test/reviews";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const editorSession = { ...adaSession, organisations: adaSession.organisations.map((o) => ({ ...o, role: "editor" as const })) };

function openAs(session = adaSession) {
  fakeAuthApi({ signedInAs: session });
  renderStudio(`/organisations/${organisationId}/settings/models`);
}

async function card() {
  return within(await screen.findByRole("region", { name: "Evaluation Model agreement" }));
}

function rows(table: HTMLElement) {
  return within(table)
    .getAllByRole("row")
    .map((row) => Array.from(row.querySelectorAll("th, td"), (cell) => cell.textContent));
}

test("every Member reads the current Evaluation Model's agreement: the rate with its interval, false passes and false fails", async () => {
  fakeModelsApi();
  fakeAgreementApi({ current: gptAgreement, reviewed: 40, reviewed_by_you: 12, skipped: 3 });
  openAs(editorSession);

  const agreement = await card();

  expect(agreement.getByText("gpt-4.1-mini (OpenAI) with guidance version 2")).toBeInTheDocument();
  expect(agreement.getByText("85% agreed")).toBeInTheDocument();
  expect(agreement.getByText("95% interval 71% to 93%")).toBeInTheDocument();
  expect(agreement.getByText("34 of 40 sample reviews agreed: 4 false passes, 2 false fails")).toBeInTheDocument();
  expect(agreement.getByText("40 sample reviews in this Organisation, 12 of them yours. 3 items skipped.")).toBeInTheDocument();
  // 40 reviews: not a Low sample overall (only its checks are).
  expect(within(agreement.getByText("85% agreed").parentElement as HTMLElement).queryByText("Low sample")).not.toBeInTheDocument();
});

test("the card breaks agreement down per check, each under 30 reviews marked Low sample", async () => {
  fakeModelsApi();
  fakeAgreementApi({ current: gptAgreement, reviewed: 40 });
  openAs();

  const agreement = await card();
  const table = agreement.getByRole("table", { name: "Agreement per check" });

  expect(rows(table)).toEqual([
    ["Check", "Reviews", "Agreed", "95% interval", "False passes", "False fails"],
    ["Grounding", "20", "90%Low sample", "70% to 97%", "1", "1"],
    ["Answers the question", "8", "75%Low sample", "41% to 93%", "2", "0"],
    ["Reference answer", "12", "83%Low sample", "55% to 95%", "1", "1"],
  ]);
  expect(within(table).getAllByTitle("Fewer than 30 sample reviews")).toHaveLength(3);
});

test("a Low sample is marked on the current figures", async () => {
  fakeModelsApi();
  fakeAgreementApi({ current: claudeAgreement, reviewed: 6 });
  openAs();

  const agreement = await card();

  expect(agreement.getByText("50% agreed")).toBeInTheDocument();
  expect(agreement.getByText("3 of 6 sample reviews agreed: 3 false passes, 0 false fails")).toBeInTheDocument();
  expect(within(agreement.getByText("50% agreed").parentElement as HTMLElement).getByTitle("Fewer than 30 sample reviews")).toHaveTextContent("Low sample");
});

test("after the Evaluation Model changed, its Judging setup's figures start afresh and the earlier ones stay listed", async () => {
  fakeModelsApi();
  fakeAgreementApi({ current: unreviewed("anthropic", "claude-sonnet-4-5"), earlier: [gptAgreement, claudeAgreement], skipped: 0 });
  openAs();

  const agreement = await card();

  expect(agreement.getByText("claude-sonnet-4-5 (Anthropic) with no guidance")).toBeInTheDocument();
  expect(agreement.getByText("No sample reviews under this Judging setup yet.")).toBeInTheDocument();
  expect(agreement.queryByRole("table", { name: "Agreement per check" })).not.toBeInTheDocument();
  expect(rows(agreement.getByRole("table", { name: "Earlier Judging setups" }))).toEqual([
    ["Judging setup", "Reviews", "Agreed", "95% interval", "False passes", "False fails"],
    ["gpt-4.1-mini (OpenAI) with guidance version 2", "40", "85%", "71% to 93%", "4", "2"],
    ["claude-haiku-4-5 (Anthropic) with no guidance", "6", "50%Low sample", "19% to 81%", "3", "0"],
  ]);
  expect(agreement.getByText("0 sample reviews in this Organisation, 0 of them yours. 0 items skipped.")).toBeInTheDocument();
});

test("after guidance is saved, the same Evaluation Model's figures start afresh and each earlier guidance version is listed apart", async () => {
  fakeModelsApi();
  fakeAgreementApi({
    current: unreviewed("openai", "gpt-4.1-mini", 3),
    earlier: [gptAgreement, { ...gptAgreement, guidance_version: null, reviews: 6, agreed: 3, rate: 0.5, low: 0.188, high: 0.812 }],
  });
  openAs();

  const agreement = await card();

  expect(agreement.getByText("gpt-4.1-mini (OpenAI) with guidance version 3")).toBeInTheDocument();
  expect(agreement.getByText("No sample reviews under this Judging setup yet.")).toBeInTheDocument();
  expect(
    rows(agreement.getByRole("table", { name: "Earlier Judging setups" }))
      .slice(1)
      .map((row) => row.slice(0, 2)),
  ).toEqual([
    ["gpt-4.1-mini (OpenAI) with guidance version 2", "40"],
    ["gpt-4.1-mini (OpenAI) with no guidance", "6"],
  ]);
});

test("one review and one skip read in the singular", async () => {
  fakeModelsApi();
  fakeAgreementApi({
    current: { ...unreviewed("openai", "gpt-4.1-mini"), reviews: 1, agreed: 1, rate: 1, low: 0.207, high: 1, checks: [] },
    reviewed: 1,
    reviewed_by_you: 1,
    skipped: 1,
  });
  openAs();

  const agreement = await card();

  expect(agreement.getByText("1 of 1 sample review agreed: 0 false passes, 0 false fails")).toBeInTheDocument();
  expect(agreement.getByText("1 sample review in this Organisation, 1 of them yours. 1 item skipped.")).toBeInTheDocument();
});

test("without a model to judge with there is nothing to agree with, but earlier Judging setups stay listed", async () => {
  fakeModelsApi();
  fakeAgreementApi({ current: null, earlier: [claudeAgreement] });
  openAs();

  const agreement = await card();

  expect(agreement.getByText("No model to judge with yet, so there is no agreement to count.")).toBeInTheDocument();
  expect(agreement.queryByText(/sample reviews? in this Organisation/)).not.toBeInTheDocument();
  expect(agreement.getByRole("table", { name: "Earlier Judging setups" })).toBeInTheDocument();
  expect(agreement.getByRole("link", { name: "Review sample" })).toBeInTheDocument();
});

test("the card links to the Review sample, and a review given there counts on return", async () => {
  fakeModelsApi();
  fakeReviewSampleApi({ items: [leaveReference], reviewed: 0 });
  openAs(editorSession);

  const agreement = await card();
  expect(agreement.getByText("No sample reviews under this Judging setup yet.")).toBeInTheDocument();
  await userEvent.click(agreement.getByRole("link", { name: "Review sample" }));
  await screen.findByRole("article", { name: "Item to review" });
  await userEvent.click(screen.getByRole("button", { name: "Skip" }));
  await userEvent.click(await screen.findByRole("button", { name: "Fail" }));
  await userEvent.click(await screen.findByRole("button", { name: "Next" }));
  await userEvent.click(await screen.findByRole("link", { name: "Back to Models settings" }));

  // The reference answer passed; the Editor failed it.
  expect(
    (await card()).getByText("0 of 1 sample review agreed: 1 false pass, 0 false fails"),
  ).toBeInTheDocument();
  expect((await card()).getByText("1 sample review in this Organisation, 1 of them yours. 1 item skipped.")).toBeInTheDocument();
});

test("agreement that can't be loaded says so", async () => {
  fakeModelsApi();
  server.use(
    http.get("*/api/organisations/:organisationId/evaluation-agreement", () => HttpResponse.json({ detail: "Down" }, { status: 503 })),
  );
  openAs();

  expect(await screen.findByText("The Evaluation Model agreement could not be loaded. Try again shortly.")).toHaveAttribute("role", "alert");
});
