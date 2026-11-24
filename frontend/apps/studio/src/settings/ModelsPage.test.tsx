import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi } from "../test/auth";
import { legalVoyage, marketingOpenAi } from "../test/credentials";
import {
  chatModels,
  claudeDefault,
  claudeJudge,
  demoCredential,
  demoDefault,
  embeddingsOnlyOpenAi,
  fakeEvaluationBudgetApi,
  fakeModelsApi,
  legalClaude,
} from "../test/models";
import { openSection } from "../test/navigation";
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

async function picker() {
  return within(await screen.findByRole("form", { name: "Choose the Default Model" }));
}

function optionNames(select: HTMLElement) {
  return within(select)
    .getAllByRole("option")
    .map((option) => option.textContent);
}

test("the Models tab is shown to every Member", async () => {
  fakeModelsApi();
  fakeAuthApi({ signedInAs: editorSession });
  renderStudio(`/organisations/${organisationId}/settings`);

  await openSection("Organisation settings", "Models");

  expect(await screen.findByRole("heading", { name: "Default Model" })).toBeInTheDocument();
});

test("an Organisation without a Default Model says so", async () => {
  fakeModelsApi();
  openAs();

  expect(await screen.findByText("No Default Model yet. New Agents need one to answer.")).toBeInTheDocument();
});

test("the credential picker offers only chat-capable credentials, and the model list is that credential's chat models", async () => {
  const api = fakeModelsApi({ credentials: [marketingOpenAi, legalVoyage, legalClaude, embeddingsOnlyOpenAi] });
  openAs();
  const form = await picker();

  const credential = form.getByRole("combobox", { name: "Credential" });
  expect(optionNames(credential)).toEqual(["Legal Claude (Anthropic)", "Marketing OpenAI (OpenAI)"]);
  expect(await form.findByRole("option", { name: "Claude Sonnet 4.5" })).toBeInTheDocument();
  expect(optionNames(form.getByRole("combobox", { name: "Model" }))).toEqual(["Claude Sonnet 4.5", "Claude Haiku 4.5"]);

  await userEvent.selectOptions(credential, "Marketing OpenAI (OpenAI)");

  expect(await form.findByRole("option", { name: "GPT-4.1 mini" })).toBeInTheDocument();
  expect(optionNames(form.getByRole("combobox", { name: "Model" }))).toEqual(["GPT-4.1", "GPT-4.1 mini"]);
  expect(api.listed).toEqual([`${legalClaude.id}/chat`, `${marketingOpenAi.id}/chat`]);
});

test("the model picker marks the models that support tools", async () => {
  chatModels[legalClaude.id]?.push({ id: "claude-no-tools", name: "Claude Plain", supports_tools: false });
  fakeModelsApi({ credentials: [legalClaude] });
  openAs();
  const form = await picker();
  await form.findByRole("option", { name: "Claude Plain" });

  const tools = form.getByRole("group", { name: "Supports tools: Agentic or Automatic" });
  expect(optionNames(tools)).toEqual(["Claude Sonnet 4.5", "Claude Haiku 4.5"]);
  const plain = form.getByRole("group", { name: "No tools: Automatic only" });
  expect(optionNames(plain)).toEqual(["Claude Plain"]);
  expect(form.queryByText(/can't use tools/)).not.toBeInTheDocument();

  await userEvent.selectOptions(form.getByRole("combobox", { name: "Model" }), "Claude Plain");

  expect(
    form.getByText("Claude Plain can't use tools: Agentic Agents that use the Default Model will answer as Automatic."),
  ).toBeInTheDocument();
  chatModels[legalClaude.id]?.pop();
});

test("a current Default Model without tool support says Agentic Agents answer as Automatic", async () => {
  fakeModelsApi({ defaultModel: { ...claudeDefault, model_name: "Claude Plain", supports_tools: false } });
  openAs(editorSession);

  expect(
    await screen.findByText("It can't use tools, so Agentic Agents without their own model answer as Automatic."),
  ).toBeInTheDocument();
});

test("an Owner sets the Default Model", async () => {
  const api = fakeModelsApi();
  openAs();
  const form = await picker();
  await userEvent.selectOptions(form.getByRole("combobox", { name: "Credential" }), "Marketing OpenAI (OpenAI)");
  await form.findByRole("option", { name: "GPT-4.1 mini" });

  await userEvent.selectOptions(form.getByRole("combobox", { name: "Model" }), "GPT-4.1 mini");
  await userEvent.click(form.getByRole("button", { name: "Save Default Model" }));

  // Confirmed by a toast.
  expect(await screen.findByRole("status")).toHaveTextContent("The Default Model is now GPT-4.1 mini.");
  expect(api.set).toEqual([{ credential_id: marketingOpenAi.id, model: "gpt-4.1-mini" }]);
  expect(await screen.findByText("GPT-4.1 mini, using Marketing OpenAI (OpenAI)")).toBeInTheDocument();
});

test("the current Default Model is shown and chosen in the picker", async () => {
  fakeModelsApi({ defaultModel: claudeDefault });
  openAs();

  expect(await screen.findByText("Claude Haiku 4.5, using Legal Claude (Anthropic)")).toBeInTheDocument();
  const form = await picker();
  expect(form.getByRole("combobox", { name: "Credential" })).toHaveDisplayValue("Legal Claude (Anthropic)");
  await form.findByRole("option", { name: "Claude Haiku 4.5" });
  expect(form.getByRole("combobox", { name: "Model" })).toHaveDisplayValue("Claude Haiku 4.5");
});

test("the seeded demo model is labelled as a demo, not a real model", async () => {
  fakeModelsApi({ defaultModel: demoDefault, credentials: [demoCredential, legalClaude] });
  openAs();

  expect(await screen.findByText("Demo model, using Northwind demo model (Demo: canned answers, not a real model)")).toBeInTheDocument();
  const form = await picker();
  expect(optionNames(form.getByRole("combobox", { name: "Credential" }))).toEqual([
    "Legal Claude (Anthropic)",
    "Northwind demo model (Demo: canned answers, not a real model)",
  ]);
});

test("Editors see the Default Model but cannot change it", async () => {
  fakeModelsApi({ defaultModel: claudeDefault });
  openAs(editorSession);

  expect(await screen.findByText("Claude Haiku 4.5, using Legal Claude (Anthropic)")).toBeInTheDocument();
  expect(screen.getByText("Only Owners can change the Default Model.")).toBeInTheDocument();
  expect(screen.queryByRole("form", { name: "Choose the Default Model" })).not.toBeInTheDocument();
});

test("a refused choice shows the API's reason", async () => {
  fakeModelsApi();
  chatModels[legalClaude.id]?.push({ id: "claude-retired", name: "Claude Retired", supports_tools: true });
  server.use(
    http.put("*/api/organisations/:organisationId/default-model", () =>
      HttpResponse.json({ detail: "Anthropic doesn't offer claude-retired for chat." }, { status: 422 }),
    ),
  );
  openAs();
  const form = await picker();
  await form.findByRole("option", { name: "Claude Retired" });

  await userEvent.selectOptions(form.getByRole("combobox", { name: "Model" }), "Claude Retired");
  await userEvent.click(form.getByRole("button", { name: "Save Default Model" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Anthropic doesn't offer claude-retired for chat.");
  chatModels[legalClaude.id]?.pop();
});

test("without a chat-capable credential, Owners are sent to add one", async () => {
  fakeModelsApi({ credentials: [legalVoyage, embeddingsOnlyOpenAi] });
  openAs();

  expect(await screen.findByText(/No credential can be used for chat yet/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Add one in Credentials" })).toHaveAttribute(
    "href",
    `/organisations/${organisationId}/settings/credentials`,
  );
  expect(screen.queryByRole("form", { name: "Choose the Default Model" })).not.toBeInTheDocument();
});

test("a Default Model that can't be loaded says so", async () => {
  fakeModelsApi();
  server.use(http.get("*/api/organisations/:organisationId/default-model", () => HttpResponse.json({ detail: "Down" }, { status: 500 })));
  openAs();

  expect(await screen.findByText("The Default Model could not be loaded. Try again shortly.")).toBeInTheDocument();
});

test("models that can't be loaded say so", async () => {
  fakeModelsApi();
  server.use(
    http.get("*/api/organisations/:organisationId/credentials/:credentialId/models/:capability", () =>
      HttpResponse.json({ detail: "Down" }, { status: 500 }),
    ),
  );
  openAs();
  const form = await picker();

  expect(await form.findByText("The models could not be loaded. Try again shortly.")).toBeInTheDocument();
  expect(form.getByRole("button", { name: "Save Default Model" })).toBeDisabled();
});

test("credentials that can't be loaded say so", async () => {
  fakeModelsApi();
  server.use(http.get("*/api/organisations/:organisationId/credentials", () => HttpResponse.json({ detail: "Down" }, { status: 500 })));
  openAs();

  expect(await screen.findByText("The credentials could not be loaded. Try again shortly.")).toBeInTheDocument();
});

test("the save button shows progress while the Default Model is saved", async () => {
  fakeModelsApi();
  server.use(http.put("*/api/organisations/:organisationId/default-model", () => delay("infinite")));
  openAs();
  const form = await picker();
  await form.findByRole("option", { name: "Claude Sonnet 4.5" });

  await userEvent.click(form.getByRole("button", { name: "Save Default Model" }));

  expect(await form.findByRole("button", { name: "Saving…" })).toBeDisabled();
});

async function evaluationSection() {
  return within(await screen.findByRole("region", { name: "Evaluation" }));
}

test("an Organisation judges with the Default Model three times until an Owner chooses otherwise", async () => {
  fakeModelsApi();
  openAs(editorSession);
  const section = await evaluationSection();

  expect(await section.findByText("Evaluation Model: the Default Model")).toBeInTheDocument();
  expect(section.getByText("Each side of a Run answers every case 3 times.")).toBeInTheDocument();
  expect(section.getByText("Only Owners can change the Evaluation Model and Evaluation repeats.")).toBeInTheDocument();
  expect(section.queryByRole("form")).not.toBeInTheDocument();
  expect(section.queryByRole("radiogroup")).not.toBeInTheDocument();
});

test("an Owner chooses the Evaluation Model, then goes back to the Default Model", async () => {
  const user = userEvent.setup();
  const { evaluation } = fakeModelsApi();
  openAs();
  const section = await evaluationSection();
  const form = within(await section.findByRole("form", { name: "Choose the Evaluation Model" }));
  const credential = form.getByRole("combobox", { name: "Judge with" });
  expect(credential).toHaveDisplayValue("Use the Default Model");
  expect(optionNames(credential)).toEqual(["Use the Default Model", "Legal Claude (Anthropic)", "Marketing OpenAI (OpenAI)"]);
  expect(form.queryByRole("combobox", { name: "Model" })).not.toBeInTheDocument();

  await user.selectOptions(credential, "Legal Claude (Anthropic)");
  await form.findByRole("option", { name: "Claude Haiku 4.5" });
  await user.selectOptions(form.getByRole("combobox", { name: "Model" }), "Claude Haiku 4.5");
  await user.click(form.getByRole("button", { name: "Save Evaluation Model" }));

  expect(await screen.findByRole("status")).toHaveTextContent("Evaluation Runs are now judged by Claude Haiku 4.5.");
  expect(await section.findByText("Evaluation Model: Claude Haiku 4.5, using Legal Claude (Anthropic)")).toBeInTheDocument();

  await user.selectOptions(credential, "Use the Default Model");
  await user.click(form.getByRole("button", { name: "Save Evaluation Model" }));

  expect(await section.findByText("Evaluation Model: the Default Model")).toBeInTheDocument();
  expect(evaluation.models).toEqual([
    { credential_id: legalClaude.id, model: "claude-haiku-4-5" },
    { credential_id: null, model: null },
  ]);
});

test("choosing the Evaluation Model reads the Evaluation Model agreement again, under the new Judging setup", async () => {
  const user = userEvent.setup();
  const { evaluation } = fakeModelsApi();
  server.use(
    http.get("*/api/organisations/:organisationId/evaluation-agreement", () =>
      HttpResponse.json(
        evaluation.models.length === 0
          ? { current: claudeAgreement, earlier: [], reviewed: 6, reviewed_by_you: 6, skipped: 0 }
          : { current: unreviewed("anthropic", "claude-sonnet-4-5"), earlier: [claudeAgreement], reviewed: 6, reviewed_by_you: 6, skipped: 0 },
      ),
    ),
  );
  openAs();
  const agreement = within(await screen.findByRole("region", { name: "Evaluation Model agreement" }));
  expect(await agreement.findByText("claude-haiku-4-5 (Anthropic) with no guidance")).toBeInTheDocument();
  const form = within(await (await evaluationSection()).findByRole("form", { name: "Choose the Evaluation Model" }));

  await user.selectOptions(form.getByRole("combobox", { name: "Judge with" }), "Legal Claude (Anthropic)");
  await form.findByRole("option", { name: "Claude Sonnet 4.5" });
  await user.selectOptions(form.getByRole("combobox", { name: "Model" }), "Claude Sonnet 4.5");
  await user.click(form.getByRole("button", { name: "Save Evaluation Model" }));

  expect(await agreement.findByText("claude-sonnet-4-5 (Anthropic) with no guidance")).toBeInTheDocument();
  expect(agreement.getByText("No sample reviews under this Judging setup yet.")).toBeInTheDocument();
});

test("the chosen Evaluation Model is shown and chosen in the picker", async () => {
  fakeModelsApi({ evaluationModel: claudeJudge });
  openAs();
  const section = await evaluationSection();

  expect(await section.findByText("Evaluation Model: Claude Sonnet 4.5, using Legal Claude (Anthropic)")).toBeInTheDocument();
  const form = within(await section.findByRole("form", { name: "Choose the Evaluation Model" }));
  expect(form.getByRole("combobox", { name: "Judge with" })).toHaveDisplayValue("Legal Claude (Anthropic)");
  await form.findByRole("option", { name: "Claude Sonnet 4.5" });
  expect(form.getByRole("combobox", { name: "Model" })).toHaveDisplayValue("Claude Sonnet 4.5");
});

test("an Owner sets the Evaluation repeats", async () => {
  const user = userEvent.setup();
  const { evaluation } = fakeModelsApi();
  openAs();
  const section = await evaluationSection();
  const repeats = await section.findByRole("radiogroup", { name: "Evaluation repeats" });
  expect(within(repeats).getAllByRole("radio").map((radio) => radio.textContent)).toEqual(["1", "3", "5", "7", "9"]);
  expect(within(repeats).getByRole("radio", { name: "3" })).toBeChecked();

  await user.click(within(repeats).getByRole("radio", { name: "5" }));

  expect(await screen.findByRole("status")).toHaveTextContent("Each side of a Run now answers every case 5 times.");
  expect(within(repeats).getByRole("radio", { name: "5" })).toBeChecked();
  expect(evaluation.repeats).toEqual([5]);
});

test("evaluation settings that can't be loaded say so", async () => {
  fakeModelsApi();
  server.use(http.get("*/api/organisations/:organisationId/evaluation-settings", () => HttpResponse.json({}, { status: 500 })));
  openAs();
  const section = await evaluationSection();

  expect(await section.findByRole("alert")).toHaveTextContent("The evaluation settings could not be loaded. Try again shortly.");
});

test("a refused Evaluation Model or repeats change says why", async () => {
  const user = userEvent.setup();
  fakeModelsApi();
  server.use(
    http.put("*/api/organisations/:organisationId/evaluation-model", async () => {
      await delay(50);
      return HttpResponse.json({ detail: "OpenAI doesn't offer gpt-0 for chat." }, { status: 422 });
    }),
    http.put("*/api/organisations/:organisationId/evaluation-repeats", () => HttpResponse.json({}, { status: 500 })),
  );
  openAs();
  const section = await evaluationSection();
  const form = within(await section.findByRole("form", { name: "Choose the Evaluation Model" }));
  await user.selectOptions(form.getByRole("combobox", { name: "Judge with" }), "Marketing OpenAI (OpenAI)");
  await form.findByRole("option", { name: "GPT-4.1 mini" });

  await user.click(form.getByRole("button", { name: "Save Evaluation Model" }));

  expect(await form.findByRole("button", { name: "Saving…" })).toBeDisabled();
  expect(await form.findByRole("alert")).toHaveTextContent("OpenAI doesn't offer gpt-0 for chat.");

  await user.click(within(section.getByRole("radiogroup", { name: "Evaluation repeats" })).getByRole("radio", { name: "7" }));

  expect(await section.findByText("Something went wrong. Try again.")).toBeInTheDocument();
  expect(section.getByText("Each side of a Run answers every case 3 times.")).toBeInTheDocument();
});

test("a credential whose models can't be loaded, or that has none, can't be saved as the Evaluation Model", async () => {
  const user = userEvent.setup();
  const empty = { ...legalClaude, id: "c0000000-0000-4000-8000-000000000009", name: "Empty Claude" };
  fakeModelsApi({ credentials: [legalClaude, empty] });
  server.use(
    http.get(`*/api/organisations/:organisationId/credentials/${legalClaude.id}/models/:capability`, () =>
      HttpResponse.json({}, { status: 500 }),
    ),
  );
  openAs();
  const section = await evaluationSection();
  const form = within(await section.findByRole("form", { name: "Choose the Evaluation Model" }));

  await user.selectOptions(form.getByRole("combobox", { name: "Judge with" }), "Legal Claude (Anthropic)");

  expect(await form.findByRole("alert")).toHaveTextContent("The models could not be loaded. Try again shortly.");
  expect(form.getByRole("button", { name: "Save Evaluation Model" })).toBeDisabled();

  await user.selectOptions(form.getByRole("combobox", { name: "Judge with" }), "Empty Claude (Anthropic)");

  expect(within(await form.findByRole("combobox", { name: "Model" })).queryAllByRole("option")).toEqual([]);
  expect(form.getByRole("button", { name: "Save Evaluation Model" })).toBeDisabled();
});

test("an Owner whose credentials can't be loaded still sets the repeats", async () => {
  fakeModelsApi();
  server.use(http.get("*/api/organisations/:organisationId/credentials", () => HttpResponse.json({}, { status: 500 })));
  openAs();
  const section = await evaluationSection();

  expect(await section.findByText("The credentials could not be loaded. Try again shortly.")).toBeInTheDocument();
  expect(section.getByRole("radiogroup", { name: "Evaluation repeats" })).toBeInTheDocument();
});

// The Evaluation budget

async function budgetPart() {
  const section = await evaluationSection();
  await section.findByRole("heading", { name: "Evaluation budget" });
  return section;
}

test("without an Evaluation budget, the Models settings say no Visitor replies are judged", async () => {
  fakeModelsApi();
  openAs(editorSession);
  const section = await budgetPart();

  expect(await section.findByText("Evaluation budget: none")).toBeInTheDocument();
  expect(section.getByText("No Evaluation budget is set, so no Visitor replies are judged.")).toBeInTheDocument();
  expect(section.queryByRole("meter")).not.toBeInTheDocument();
});

test("Editors see the Evaluation budget and this month's meter beside the evaluation settings, but cannot change it", async () => {
  fakeModelsApi();
  fakeEvaluationBudgetApi({ budget: "50.00", spent: "12.5" });
  openAs(editorSession);
  const section = await budgetPart();

  expect(await section.findByText("Evaluation budget: $50.00 a month")).toBeInTheDocument();
  const meter = section.getByRole("meter", { name: "Evaluation budget spent this month" });
  expect(meter).toHaveAttribute("aria-valuetext", "$12.50 of $50.00");
  expect(section.getByText(/Judgements already under way when the budget is reached still finish/)).toBeInTheDocument();
  expect(section.getByText("Only Owners can change the Evaluation budget.")).toBeInTheDocument();
  expect(section.queryByRole("form", { name: "Set the Evaluation budget" })).not.toBeInTheDocument();
  expect(section.queryByRole("spinbutton")).not.toBeInTheDocument();
});

test("a spent Evaluation budget says judging is paused until the 1st", async () => {
  fakeModelsApi();
  fakeEvaluationBudgetApi({ budget: "10.00", spent: "10.04" });
  openAs();
  const section = await budgetPart();

  const meter = await section.findByRole("meter", { name: "Evaluation budget spent this month" });
  expect(meter).toHaveAttribute("aria-valuetext", "$10.04 of $10.00");
  expect(
    section.getByText(/Spent: no Visitor replies are judged until the budget is raised or the month ends on 1 December 2026 \(UTC\)\./),
  ).toBeInTheDocument();
});

test("an Owner sets the Evaluation budget, then removes it", async () => {
  const user = userEvent.setup();
  fakeModelsApi();
  const budget = fakeEvaluationBudgetApi();
  openAs();
  const section = await budgetPart();
  const form = within(await section.findByRole("form", { name: "Set the Evaluation budget" }));
  const amount = form.getByRole("spinbutton", { name: "Evaluation budget (US dollars a month)" });
  expect(amount).toHaveAccessibleDescription(
    "The most Live Verdicts may spend each calendar month (UTC). Once it is spent, sampling pauses across the Organisation until the 1st and every Owner is emailed once. Evaluation Runs are never capped.",
  );
  expect(form.queryByRole("button", { name: "Remove Evaluation budget" })).not.toBeInTheDocument();

  await user.type(amount, "25");
  await user.click(form.getByRole("button", { name: "Save Evaluation budget" }));

  expect(await screen.findByRole("status")).toHaveTextContent("The Evaluation budget is now $25.00 a month.");
  expect(await section.findByText("Evaluation budget: $25.00 a month")).toBeInTheDocument();
  expect(section.getByRole("meter", { name: "Evaluation budget spent this month" })).toHaveAttribute("aria-valuetext", "$0.00 of $25.00");

  await user.click(form.getByRole("button", { name: "Remove Evaluation budget" }));

  expect(await section.findByText("Evaluation budget: none")).toBeInTheDocument();
  expect(budget.set).toEqual(["25", null]);
});

test("a refused Evaluation budget says why", async () => {
  const user = userEvent.setup();
  fakeModelsApi();
  server.use(
    http.put("*/api/organisations/:organisationId/evaluation-budget", async () => {
      await delay(50);
      return HttpResponse.json({ detail: "Only Owners can do this." }, { status: 403 });
    }),
  );
  openAs();
  const form = within(await (await budgetPart()).findByRole("form", { name: "Set the Evaluation budget" }));

  await user.type(form.getByRole("spinbutton"), "5");
  await user.click(form.getByRole("button", { name: "Save Evaluation budget" }));

  expect(await form.findByRole("button", { name: "Saving…" })).toBeDisabled();
  expect(await form.findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});

test("an Evaluation budget that can't be loaded says so", async () => {
  fakeModelsApi();
  server.use(http.get("*/api/organisations/:organisationId/evaluation-budget", () => HttpResponse.json({}, { status: 500 })));
  openAs();
  const section = await budgetPart();

  expect(await section.findByText("The Evaluation budget could not be loaded. Try again shortly.")).toBeInTheDocument();
  expect(section.queryByRole("form", { name: "Set the Evaluation budget" })).not.toBeInTheDocument();
});
