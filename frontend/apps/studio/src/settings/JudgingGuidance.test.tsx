import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi } from "../test/auth";
import {
  DRAFTED_GUIDANCE,
  fakeGuidanceJobApi,
  fakeJudgingGuidanceApi,
  fakeModelsApi,
  guidanceCheck,
  guidanceDraft,
  guidanceDrafting,
  guidanceVersion,
  PARTIAL_GUIDANCE,
} from "../test/models";
import { renderStudio } from "../test/render";
import { claudeAgreement, unreviewed } from "../test/reviews";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const modelsPath = `/organisations/${organisationId}/settings/models`;
const editorSession = { ...adaSession, organisations: adaSession.organisations.map((o) => ({ ...o, role: "editor" as const })) };

function openAs(session = adaSession) {
  fakeAuthApi({ signedInAs: session });
  renderStudio(modelsPath);
}

async function card() {
  return within(await screen.findByRole("region", { name: "Judging guidance" }));
}

/** Confirms the save dialog the form's Save guidance opens. */
async function confirmSave(user: ReturnType<typeof userEvent.setup>) {
  const dialog = within(await screen.findByRole("dialog", { name: "Save the Judging guidance?" }));
  await user.click(dialog.getByRole("button", { name: "Save guidance" }));
}

test("an Organisation without guidance says the Evaluation Model judges by its own instructions", async () => {
  fakeModelsApi();
  openAs();
  const section = await card();

  expect(await section.findByText("No guidance: the Evaluation Model judges by its own instructions alone.")).toBeInTheDocument();
  expect(section.queryByRole("list", { name: "Guidance versions" })).not.toBeInTheDocument();
  expect(section.queryByRole("button", { name: "Remove guidance" })).not.toBeInTheDocument();
});

test("Editors read the current guidance and its versions, but cannot change it", async () => {
  fakeModelsApi();
  fakeJudgingGuidanceApi({ versions: [guidanceVersion(2, PARTIAL_GUIDANCE), guidanceVersion(1, "", null)] });
  openAs(editorSession);
  const section = await card();

  const current = within(await section.findByRole("group", { name: "Current guidance" }));
  expect(current.getByText(PARTIAL_GUIDANCE)).toBeInTheDocument();
  expect(current.getByText("Version 2, saved by Ada Lovelace on 12 November 2026")).toBeInTheDocument();
  const history = within(section.getByRole("list", { name: "Guidance versions" }));
  const items = history.getAllByRole("listitem");
  expect(items.map((item) => item.querySelector("p")?.textContent)).toEqual([
    "Version 2, written, saved by Ada Lovelace on 12 November 2026",
    "Version 1, written, saved by a deleted Member on 11 November 2026",
  ]);
  expect(within(items[1] as HTMLElement).getByText("No guidance (removed)")).toBeInTheDocument();
  expect(section.getByText("Only Owners can change the Judging guidance.")).toBeInTheDocument();
  expect(section.queryByRole("button", { name: "Edit guidance" })).not.toBeInTheDocument();
});

test("an Owner writes and saves guidance as a new version", async () => {
  const user = userEvent.setup();
  fakeModelsApi();
  const api = fakeJudgingGuidanceApi();
  openAs();
  const section = await card();

  await user.click(await section.findByRole("button", { name: "Edit guidance" }));
  const form = within(section.getByRole("form", { name: "Edit the Judging guidance" }));
  const editor = form.getByRole("textbox", { name: "Judging guidance" });
  expect(editor).toHaveFocus();
  expect(editor).toHaveAccessibleDescription(
    "0 of 2,000 characters. Every save starts a new Judging setup: new Evaluation Runs and Live Verdicts are judged with it, and earlier ones keep theirs. Evaluation Model agreement starts again under it, and the Live score drop alert stays quiet for the previous Live Version until that Version has 30 Live Verdicts under it.",
  );
  await user.type(editor, PARTIAL_GUIDANCE);
  expect(form.getByText(`${String(PARTIAL_GUIDANCE.length)} of 2,000 characters.`, { exact: false })).toBeInTheDocument();
  await user.click(form.getByRole("button", { name: "Save guidance" }));
  // Unchecked text is saved after a confirmation that says so.
  expect(await screen.findByRole("dialog", { name: "Save the Judging guidance?" })).toHaveAccessibleDescription(
    "New Evaluation Runs and Live Verdicts are judged with it, and it starts a new Judging setup. This text hasn't been checked on held-out reviews.",
  );
  await confirmSave(user);

  expect(await screen.findByRole("status")).toHaveTextContent("Judging guidance version 1 is saved: new judgements use it.");
  expect(within(await section.findByRole("group", { name: "Current guidance" })).getByText(PARTIAL_GUIDANCE)).toBeInTheDocument();
  expect(section.queryByRole("form", { name: "Edit the Judging guidance" })).not.toBeInTheDocument();
  expect(api.saved).toEqual([PARTIAL_GUIDANCE]);
});

test("saving guidance reads the Evaluation Model agreement again, under the new Judging setup", async () => {
  const user = userEvent.setup();
  fakeModelsApi();
  const api = fakeJudgingGuidanceApi();
  server.use(
    http.get("*/api/organisations/:organisationId/evaluation-agreement", () =>
      HttpResponse.json(
        api.saved.length === 0
          ? { current: claudeAgreement, earlier: [], reviewed: 6, reviewed_by_you: 6, skipped: 0 }
          : { current: unreviewed("anthropic", "claude-haiku-4-5", 1), earlier: [claudeAgreement], reviewed: 6, reviewed_by_you: 6, skipped: 0 },
      ),
    ),
  );
  openAs();
  const section = await card();
  const agreement = within(await screen.findByRole("region", { name: "Evaluation Model agreement" }));
  expect(await agreement.findByText("claude-haiku-4-5 (Anthropic) with no guidance")).toBeInTheDocument();

  await user.click(await section.findByRole("button", { name: "Edit guidance" }));
  await user.type(section.getByRole("textbox", { name: "Judging guidance" }), PARTIAL_GUIDANCE);
  await user.click(section.getByRole("button", { name: "Save guidance" }));
  await confirmSave(user);

  expect(await agreement.findByText("claude-haiku-4-5 (Anthropic) with guidance version 1")).toBeInTheDocument();
  expect(agreement.getByText("No sample reviews under this Judging setup yet.")).toBeInTheDocument();
});

test("an Owner cancels an edit without saving", async () => {
  const user = userEvent.setup();
  fakeModelsApi();
  const api = fakeJudgingGuidanceApi({ versions: [guidanceVersion(1, PARTIAL_GUIDANCE)] });
  openAs();
  const section = await card();

  await user.click(await section.findByRole("button", { name: "Edit guidance" }));
  const editor = section.getByRole("textbox", { name: "Judging guidance" });
  expect(editor).toHaveValue(PARTIAL_GUIDANCE);
  await user.clear(editor);
  await user.click(section.getByRole("button", { name: "Cancel" }));

  expect(section.queryByRole("textbox")).not.toBeInTheDocument();
  expect(api.saved).toEqual([]);
});

test("guidance longer than 2,000 characters can't be saved", async () => {
  const user = userEvent.setup();
  fakeModelsApi();
  fakeJudgingGuidanceApi({ versions: [guidanceVersion(1, "x".repeat(2000))] });
  openAs();
  const section = await card();
  await user.click(await section.findByRole("button", { name: "Edit guidance" }));
  const editor = section.getByRole("textbox", { name: "Judging guidance" });

  await user.type(editor, "y");

  expect(editor).toHaveAttribute("aria-invalid", "true");
  expect(section.getByText(/2,001 of 2,000 characters/)).toBeInTheDocument();
  expect(section.getByRole("button", { name: "Save guidance" })).toBeDisabled();
});

test("an Owner removes guidance after confirming, saving an empty version", async () => {
  const user = userEvent.setup();
  fakeModelsApi();
  const api = fakeJudgingGuidanceApi({ versions: [guidanceVersion(1, PARTIAL_GUIDANCE)] });
  openAs();
  const section = await card();

  await user.click(await section.findByRole("button", { name: "Remove guidance" }));
  const dialog = within(await screen.findByRole("alertdialog", { name: "Remove the Judging guidance?" }));
  // Before removing, it says what a new Judging setup restarts.
  expect(dialog.getByText(/It starts a new Judging setup/)).toHaveTextContent(
    "It starts a new Judging setup: Evaluation Model agreement starts again, and the Live score drop alert stays quiet for the previous Live Version until that Version has 30 Live Verdicts under it.",
  );
  await user.click(dialog.getByRole("button", { name: "Remove guidance" }));

  expect(await screen.findByRole("status")).toHaveTextContent("Judging guidance is removed: new judgements use the Evaluation Model's own instructions.");
  expect(await section.findByText("No guidance: the Evaluation Model judges by its own instructions alone.")).toBeInTheDocument();
  expect(api.saved).toEqual([""]);
});

test("an Owner who changes their mind keeps the guidance", async () => {
  const user = userEvent.setup();
  fakeModelsApi();
  const api = fakeJudgingGuidanceApi({ versions: [guidanceVersion(1, PARTIAL_GUIDANCE)] });
  openAs();
  const section = await card();

  await user.click(await section.findByRole("button", { name: "Remove guidance" }));
  await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Cancel" }));

  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  expect(api.saved).toEqual([]);
});

test("a refused save says why and keeps the edit", async () => {
  const user = userEvent.setup();
  fakeModelsApi();
  server.use(
    http.put("*/api/organisations/:organisationId/judging-guidance", async () => {
      await delay(50);
      return HttpResponse.json({ detail: "Only Owners can do this." }, { status: 403 });
    }),
  );
  openAs();
  const section = await card();
  await user.click(await section.findByRole("button", { name: "Edit guidance" }));

  await user.type(section.getByRole("textbox", { name: "Judging guidance" }), "Be fair.");
  await user.click(section.getByRole("button", { name: "Save guidance" }));
  const dialog = within(await screen.findByRole("dialog", { name: "Save the Judging guidance?" }));
  await user.click(dialog.getByRole("button", { name: "Save guidance" }));

  expect(dialog.getByRole("button", { name: "Save guidance" })).toBeDisabled();
  expect(await dialog.findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
  await user.click(dialog.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(section.getByRole("textbox", { name: "Judging guidance" })).toHaveValue("Be fair.");
});

test("guidance that can't be loaded says so", async () => {
  fakeModelsApi();
  server.use(http.get("*/api/organisations/:organisationId/judging-guidance", () => HttpResponse.json({}, { status: 500 })));
  openAs();
  const section = await card();

  expect(await section.findByText("The Judging guidance could not be loaded. Try again shortly.")).toBeInTheDocument();
  expect(section.queryByRole("button", { name: "Edit guidance" })).not.toBeInTheDocument();
});

test("clearing the editor and saving removes the guidance", async () => {
  const user = userEvent.setup();
  fakeModelsApi();
  const api = fakeJudgingGuidanceApi({ versions: [guidanceVersion(1, PARTIAL_GUIDANCE)] });
  openAs();
  const section = await card();
  await user.click(await section.findByRole("button", { name: "Edit guidance" }));

  await user.clear(section.getByRole("textbox", { name: "Judging guidance" }));
  await user.click(section.getByRole("button", { name: "Save guidance" }));
  await confirmSave(user);

  expect(await screen.findByRole("status")).toHaveTextContent("Judging guidance is removed: new judgements use the Evaluation Model's own instructions.");
  expect(api.saved).toEqual([""]);
});

test("saving nothing when there is no guidance keeps there being none", async () => {
  const user = userEvent.setup();
  fakeModelsApi();
  const api = fakeJudgingGuidanceApi();
  openAs();
  const section = await card();
  await user.click(await section.findByRole("button", { name: "Edit guidance" }));

  await user.click(section.getByRole("button", { name: "Save guidance" }));
  await confirmSave(user);

  expect(await screen.findByRole("status")).toHaveTextContent("Judging guidance is removed");
  expect(section.getByText("No guidance: the Evaluation Model judges by its own instructions alone.")).toBeInTheDocument();
  expect(api.saved).toEqual([""]);
});

// Checking guidance on held-out reviews (ticket 19-04)

async function editing(user: ReturnType<typeof userEvent.setup>) {
  const section = await card();
  await user.click(await section.findByRole("button", { name: "Edit guidance" }));
  return section;
}

test("an Owner checks guidance on held-out reviews and reads its progress, then its result", async () => {
  const user = userEvent.setup();
  fakeModelsApi();
  fakeJudgingGuidanceApi();
  const api = fakeGuidanceJobApi({ then: [{ status: "running", judged: 6, agreed: 5, agreed_before: 3 }, { ...guidanceCheck(PARTIAL_GUIDANCE), id: "job-2" }] });
  openAs();
  const section = await editing(user);
  await user.type(section.getByRole("textbox", { name: "Judging guidance" }), PARTIAL_GUIDANCE);

  await user.click(section.getByRole("button", { name: "Check guidance" }));

  const result = within(section.getByRole("group", { name: "Check result" }));
  expect(await result.findByText("Checking on 12 held-out reviews…")).toBeInTheDocument();
  expect(result.getByRole("meter", { name: "Check progress" })).toHaveAttribute("aria-valuetext", "0 of 12 reviews");
  expect(section.getByRole("button", { name: "Check guidance" })).toBeDisabled();
  await waitFor(
    () => {
      expect(result.getByRole("meter", { name: "Check progress" })).toHaveAttribute("aria-valuetext", "6 of 12 reviews");
    },
    { timeout: 3000 },
  );
  expect(await result.findByText("On held-out reviews, this guidance would agree on 10 of 12 (now 7).", {}, { timeout: 3000 })).toBeInTheDocument();
  expect(result.getByText("Low sample")).toBeInTheDocument();
  expect(result.getByText("False passes: 1, false fails: 1. Cost $0.0034.")).toBeInTheDocument();
  expect(section.getByRole("button", { name: "Check again" })).toBeEnabled();
  expect(api.started).toEqual([PARTIAL_GUIDANCE]);
});

test("editing the text marks the check out of date", async () => {
  const user = userEvent.setup();
  fakeModelsApi();
  fakeJudgingGuidanceApi({ versions: [guidanceVersion(1, PARTIAL_GUIDANCE)] });
  fakeGuidanceJobApi({ latest: guidanceCheck(PARTIAL_GUIDANCE, { left_out: 2, low_sample: false }) });
  openAs();
  const section = await editing(user);
  const result = within(section.getByRole("group", { name: "Check result" }));
  expect(await result.findByText("False passes: 1, false fails: 1. 2 left out: their replies were deleted. Cost $0.0034.")).toBeInTheDocument();
  expect(result.queryByText("Low sample")).not.toBeInTheDocument();
  expect(result.queryByRole("status")).not.toBeInTheDocument();

  await user.type(section.getByRole("textbox", { name: "Judging guidance" }), " Always.");

  expect(result.getByRole("status")).toHaveTextContent("Out of date: the text has changed since this check. Check again before saving.");
  expect(section.getByRole("button", { name: "Check guidance" })).toBeEnabled();
});

test("the save dialog warns when the check shows lower agreement, and still saves", async () => {
  const user = userEvent.setup();
  fakeModelsApi();
  const guidance = fakeJudgingGuidanceApi();
  fakeGuidanceJobApi({ latest: guidanceCheck("Be strict.", { agreed: 5 }) });
  openAs();
  const section = await editing(user);
  await user.type(section.getByRole("textbox", { name: "Judging guidance" }), "Be strict.");

  await user.click(section.getByRole("button", { name: "Save guidance" }));

  const dialog = within(await screen.findByRole("dialog", { name: "Save the Judging guidance?" }));
  expect(dialog.getByRole("status")).toHaveTextContent(
    "The latest check shows lower agreement: on held-out reviews this guidance would agree on 5 of 12 (now 7). You can still save it.",
  );
  expect(await screen.findByRole("dialog")).toHaveAccessibleDescription("New Evaluation Runs and Live Verdicts are judged with it, and it starts a new Judging setup.");
  await user.click(dialog.getByRole("button", { name: "Save guidance" }));
  expect(await screen.findByText("Judging guidance version 1 is saved: new judgements use it.")).toBeInTheDocument();
  expect(guidance.saved).toEqual(["Be strict."]);
});

test("a check showing higher agreement saves without a warning", async () => {
  const user = userEvent.setup();
  fakeModelsApi();
  fakeJudgingGuidanceApi();
  fakeGuidanceJobApi({ latest: guidanceCheck("Be strict.") });
  openAs();
  const section = await editing(user);
  await user.type(section.getByRole("textbox", { name: "Judging guidance" }), "Be strict.");

  await user.click(section.getByRole("button", { name: "Save guidance" }));

  const dialog = within(await screen.findByRole("dialog", { name: "Save the Judging guidance?" }));
  expect(dialog.queryByRole("status")).not.toBeInTheDocument();
});

test("an Owner cancels a check in progress", async () => {
  const user = userEvent.setup();
  fakeModelsApi();
  fakeJudgingGuidanceApi();
  const api = fakeGuidanceJobApi({ latest: guidanceCheck("Be strict.", { status: "queued", judged: 0 }) });
  openAs();
  const section = await editing(user);
  const result = within(section.getByRole("group", { name: "Check result" }));

  await user.click(await result.findByRole("button", { name: "Cancel check" }));

  expect(await result.findByText("The check was cancelled.")).toBeInTheDocument();
  expect(api.cancelled).toEqual(["job-1"]);
});

test("a refused cancel says why", async () => {
  const user = userEvent.setup();
  fakeModelsApi();
  fakeJudgingGuidanceApi();
  fakeGuidanceJobApi({ latest: guidanceCheck("Be strict.", { status: "running", judged: 3 }) });
  server.use(
    http.post("*/api/organisations/:organisationId/guidance-jobs/:jobId/cancel", () =>
      HttpResponse.json({ detail: "Only a draft or check in progress can be cancelled." }, { status: 409 }),
    ),
  );
  openAs();
  const section = await editing(user);

  await user.click(await section.findByRole("button", { name: "Cancel check" }));

  expect(await section.findByRole("alert")).toHaveTextContent("Only a draft or check in progress can be cancelled.");
});

test("a failed check says why", async () => {
  const user = userEvent.setup();
  fakeModelsApi();
  fakeJudgingGuidanceApi();
  fakeGuidanceJobApi({ latest: guidanceCheck("Be strict.", { status: "failed", error_reason: "The Evaluation Model didn't answer in time." }) });
  openAs();
  const section = await editing(user);

  expect(await section.findByRole("alert")).toHaveTextContent("The check failed: The Evaluation Model didn't answer in time.");
});

test("a refused check says why", async () => {
  const user = userEvent.setup();
  fakeModelsApi();
  fakeJudgingGuidanceApi();
  server.use(
    http.post("*/api/organisations/:organisationId/judging-guidance/checks", () =>
      HttpResponse.json({ detail: "A check needs at least 2 Review sample reviews under the current Judging setup." }, { status: 422 }),
    ),
  );
  openAs();
  const section = await editing(user);

  await user.click(section.getByRole("button", { name: "Check guidance" }));

  expect(await section.findByRole("alert")).toHaveTextContent("A check needs at least 2 Review sample reviews under the current Judging setup.");
  await user.type(section.getByRole("textbox", { name: "Judging guidance" }), "x");
  expect(section.queryByRole("alert")).not.toBeInTheDocument();
});

test("a saved version shows the check it kept", async () => {
  const check = { reviews: 40, agreed: 36, false_passes: 1, false_fails: 3, agreed_before: 31, low_sample: false };
  fakeModelsApi();
  fakeJudgingGuidanceApi({ versions: [guidanceVersion(2, PARTIAL_GUIDANCE, "Ada Lovelace", check), guidanceVersion(1, "Be strict.", "Ada Lovelace", { ...check, reviews: 12, low_sample: true })] });
  openAs(editorSession);
  const section = await card();

  const current = within(await section.findByRole("group", { name: "Current guidance" }));
  expect(current.getByText("Checked before saving: would agree on 36 of 40 (now 31), false passes: 1, false fails: 3.")).toBeInTheDocument();
  expect(current.queryByText("Low sample")).not.toBeInTheDocument();
  const [, earlier] = within(section.getByRole("list", { name: "Guidance versions" })).getAllByRole("listitem");
  expect(within(earlier as HTMLElement).getByText("Low sample")).toBeInTheDocument();
});

test("an Owner can still check and save when the latest check can't be loaded", async () => {
  const user = userEvent.setup();
  fakeModelsApi();
  fakeJudgingGuidanceApi();
  let reads = 0;
  server.use(
    http.get("*/api/organisations/:organisationId/guidance-jobs/latest", () => {
      reads += 1;
      return HttpResponse.json({ detail: "Something broke." }, { status: 500 });
    }),
  );
  openAs();
  const section = await editing(user);

  await waitFor(() => {
    expect(reads).toBeGreaterThan(0);
  });
  expect(section.getByRole("group", { name: "Check result" })).toBeEmptyDOMElement();
  expect(section.getByRole("button", { name: "Check guidance" })).toBeEnabled();
});

// Drafting guidance from disagreements (ticket 19-05)

async function drafting() {
  return within(await (await card()).findByRole("group", { name: "Draft guidance" }));
}

const MISSING =
  "Drafting needs 10 disagreeing reviews and 30 Review sample reviews under the current Judging setup: 6 more disagreeing reviews and 26 more Review sample reviews.";

test("the Draft button says what is missing until there are enough reviews", async () => {
  fakeModelsApi();
  fakeGuidanceJobApi({ drafting: guidanceDrafting({ disagreements: 4, sample_reviews: 4, offered: false, missing: MISSING }) });
  openAs();
  const group = await drafting();

  const draft = group.getByRole("button", { name: "Draft guidance" });
  await waitFor(() => {
    expect(draft).toHaveAccessibleDescription(MISSING);
  });
  expect(draft).toBeDisabled();
});

test("without a model to judge with, drafting says so", async () => {
  fakeModelsApi();
  openAs();
  const group = await drafting();

  const draft = group.getByRole("button", { name: "Draft guidance" });
  await waitFor(() => {
    expect(draft).toHaveAccessibleDescription("The Organisation has neither an Evaluation Model nor a Default Model to judge with.");
  });
  expect(draft).toBeDisabled();
});

test("Editors are not offered drafting", async () => {
  fakeModelsApi();
  openAs(editorSession);
  const section = await card();

  expect(await section.findByText("Only Owners can change the Judging guidance.")).toBeInTheDocument();
  expect(section.queryByRole("group", { name: "Draft guidance" })).not.toBeInTheDocument();
});

test("an Owner drafts guidance after reading its estimated Cost, follows it and opens it with its explanation", async () => {
  const user = userEvent.setup();
  fakeModelsApi();
  fakeJudgingGuidanceApi();
  const api = fakeGuidanceJobApi({ then: [{ status: "running", reviews_read: 14 }, guidanceDraft("")] });
  openAs();
  const group = await drafting();
  const draft = group.getByRole("button", { name: "Draft guidance" });
  await waitFor(() => {
    expect(draft).toBeEnabled();
  });
  expect(draft).not.toHaveAccessibleDescription();

  await user.click(draft);
  const dialog = await screen.findByRole("dialog", { name: "Draft guidance from disagreements?" });
  expect(dialog).toHaveAccessibleDescription(
    "The Evaluation Model reads about 15 disagreeing reviews and the current guidance. Estimated Cost: $0.0106. It counts in Organisation cost, never against the Evaluation budget.",
  );
  await user.click(within(dialog).getByRole("button", { name: "Draft guidance" }));

  expect(await group.findByText("Drafting guidance: waiting to start…")).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(api.drafts).toHaveLength(1);
  expect(group.getByRole("button", { name: "Draft guidance" })).toBeDisabled();
  expect(await group.findByText("Drafting guidance from 14 disagreeing reviews…", {}, { timeout: 3000 })).toBeInTheDocument();
  expect(await group.findByText("A draft from 14 disagreeing reviews is ready to edit, check and save.", {}, { timeout: 3000 })).toBeInTheDocument();

  await user.click(group.getByRole("button", { name: "Open the draft" }));

  const section = await card();
  expect(section.getByRole("textbox", { name: "Judging guidance" })).toHaveValue(DRAFTED_GUIDANCE);
  const explanation = within(section.getByRole("group", { name: "The draft's explanation" }));
  expect(
    explanation.getByText(
      "Drafted by the Evaluation Model from 14 disagreeing reviews outside the held-out half. Edit it, check it on the held-out reviews, then save it.",
    ),
  ).toBeInTheDocument();
  expect(explanation.getAllByRole("listitem").map((item) => item.textContent)).toEqual([
    "Partial answers that say what they don't cover pass. (answers 3 disagreeing reviews)",
    "Judge grounding by the cited excerpts alone. (answers 1 disagreeing review)",
  ]);
  // A draft is no check: there is no check result yet.
  expect(section.getByRole("group", { name: "Check result" })).toBeEmptyDOMElement();
});

test("an Owner edits a draft, checks it and saves it as a drafted version", async () => {
  const user = userEvent.setup();
  fakeModelsApi();
  const guidance = fakeJudgingGuidanceApi();
  const jobs = fakeGuidanceJobApi({ latest: guidanceDraft("") });
  openAs();
  const group = await drafting();
  await user.click(await group.findByRole("button", { name: "Open the draft" }));
  const section = await card();
  await user.type(section.getByRole("textbox", { name: "Judging guidance" }), " Be brief.");

  await user.click(section.getByRole("button", { name: "Check guidance" }));

  expect(await section.findByText("Checking on 12 held-out reviews…")).toBeInTheDocument();
  expect(jobs.started).toEqual([`${DRAFTED_GUIDANCE} Be brief.`]);
  expect(section.getByRole("group", { name: "The draft's explanation" })).toBeInTheDocument();
  await user.click(section.getByRole("button", { name: "Save guidance" }));
  await confirmSave(user);

  expect(await screen.findByRole("status")).toHaveTextContent("Judging guidance version 1 is saved");
  expect(guidance.saved).toEqual([`${DRAFTED_GUIDANCE} Be brief.`]);
  expect(guidance.draftIds).toEqual(["draft-1"]);
  const history = within(section.getByRole("list", { name: "Guidance versions" }));
  expect(history.getByText("Version 1, drafted, saved by Ada Lovelace on 11 November 2026")).toBeInTheDocument();
  // The draft is saved over: it is not offered again.
  expect(section.queryByRole("button", { name: "Open the draft" })).not.toBeInTheDocument();
});

test("guidance written by hand is saved as written", async () => {
  const user = userEvent.setup();
  fakeModelsApi();
  const guidance = fakeJudgingGuidanceApi();
  openAs();
  const section = await editing(user);
  await user.type(section.getByRole("textbox", { name: "Judging guidance" }), PARTIAL_GUIDANCE);

  await user.click(section.getByRole("button", { name: "Save guidance" }));
  await confirmSave(user);

  expect(await screen.findByRole("status")).toHaveTextContent("Judging guidance version 1 is saved");
  expect(guidance.draftIds).toEqual([null]);
});

test("a draft of guidance since replaced is not offered", async () => {
  fakeModelsApi();
  fakeJudgingGuidanceApi({ versions: [guidanceVersion(1, PARTIAL_GUIDANCE)] });
  fakeGuidanceJobApi({ latest: guidanceDraft("") });
  openAs();
  const group = await drafting();

  await waitFor(() => {
    expect(group.getByRole("button", { name: "Draft guidance" })).toBeEnabled();
  });
  expect(group.queryByRole("button", { name: "Open the draft" })).not.toBeInTheDocument();
});

test("an Owner cancels a draft in progress", async () => {
  const user = userEvent.setup();
  fakeModelsApi();
  fakeJudgingGuidanceApi();
  const api = fakeGuidanceJobApi({ latest: guidanceDraft("", { status: "running", draft: null, finished_at: null }) });
  openAs();
  const group = await drafting();

  await user.click(await group.findByRole("button", { name: "Cancel draft" }));

  expect(await group.findByText("The draft was cancelled.")).toBeInTheDocument();
  expect(api.cancelled).toEqual(["draft-1"]);
});

test("a refused draft cancel says why", async () => {
  const user = userEvent.setup();
  fakeModelsApi();
  fakeJudgingGuidanceApi();
  fakeGuidanceJobApi({ latest: guidanceDraft("", { status: "running", draft: null }) });
  server.use(
    http.post("*/api/organisations/:organisationId/guidance-jobs/:jobId/cancel", () =>
      HttpResponse.json({ detail: "Only a draft or check in progress can be cancelled." }, { status: 409 }),
    ),
  );
  openAs();
  const group = await drafting();

  await user.click(await group.findByRole("button", { name: "Cancel draft" }));

  expect(await group.findByRole("alert")).toHaveTextContent("Only a draft or check in progress can be cancelled.");
});

test("a failed draft says why", async () => {
  fakeModelsApi();
  fakeJudgingGuidanceApi();
  const reason = "The Evaluation Model couldn't draft guidance: the provider is unavailable.";
  fakeGuidanceJobApi({ latest: guidanceDraft("", { status: "failed", draft: null, error_reason: reason }) });
  openAs();
  const group = await drafting();

  expect(await group.findByRole("alert")).toHaveTextContent(`The draft failed: ${reason}`);
});

test("a refused draft says why in its dialog, which can be closed", async () => {
  const user = userEvent.setup();
  fakeModelsApi();
  fakeJudgingGuidanceApi();
  fakeGuidanceJobApi({ drafting: guidanceDrafting({ estimated_cost_usd: null }) });
  server.use(
    http.post("*/api/organisations/:organisationId/judging-guidance/drafts", () =>
      HttpResponse.json({ detail: "A draft or check is already in progress in the Organisation." }, { status: 409 }),
    ),
  );
  openAs();
  const group = await drafting();
  const draft = group.getByRole("button", { name: "Draft guidance" });
  await waitFor(() => {
    expect(draft).toBeEnabled();
  });
  await user.click(draft);
  const dialog = await screen.findByRole("dialog", { name: "Draft guidance from disagreements?" });
  expect(dialog).toHaveAccessibleDescription(expect.stringContaining("Estimated Cost: unknown (the model has no price)."));

  await user.click(within(dialog).getByRole("button", { name: "Draft guidance" }));

  expect(await within(dialog).findByRole("alert")).toHaveTextContent("A draft or check is already in progress in the Organisation.");
  await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
