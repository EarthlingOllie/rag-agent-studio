import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi } from "../test/auth";
import { legalVoyage, marketingOpenAi } from "../test/credentials";
import { chatModels, claudeDefault, demoCredential, demoDefault, embeddingsOnlyOpenAi, fakeModelsApi, legalClaude } from "../test/models";
import { openSection } from "../test/navigation";
import { renderStudio } from "../test/render";
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
