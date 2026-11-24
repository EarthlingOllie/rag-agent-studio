import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi } from "../test/auth";
import { fakeJudgingGuidanceApi, fakeModelsApi, guidanceVersion, PARTIAL_GUIDANCE } from "../test/models";
import { renderStudio } from "../test/render";
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
    "0 of 2,000 characters. Every save starts a new Judging setup: new Evaluation Runs and Live Verdicts are judged with it, and earlier ones keep theirs.",
  );
  await user.type(editor, PARTIAL_GUIDANCE);
  expect(form.getByText(`${String(PARTIAL_GUIDANCE.length)} of 2,000 characters.`, { exact: false })).toBeInTheDocument();
  await user.click(form.getByRole("button", { name: "Save guidance" }));

  expect(await screen.findByRole("status")).toHaveTextContent("Judging guidance version 1 is saved: new judgements use it.");
  expect(within(await section.findByRole("group", { name: "Current guidance" })).getByText(PARTIAL_GUIDANCE)).toBeInTheDocument();
  expect(section.queryByRole("form", { name: "Edit the Judging guidance" })).not.toBeInTheDocument();
  expect(api.saved).toEqual([PARTIAL_GUIDANCE]);
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

  expect(await section.findByRole("button", { name: "Saving…" })).toBeDisabled();
  expect(await section.findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
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

  expect(await screen.findByRole("status")).toHaveTextContent("Judging guidance is removed");
  expect(section.getByText("No guidance: the Evaluation Model judges by its own instructions alone.")).toBeInTheDocument();
  expect(api.saved).toEqual([""]);
});
