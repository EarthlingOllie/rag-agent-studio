import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";

import { claude, defaultDraft, fakeAgentsApi, hrHelper, hrTag, openAi, payTag, voyage } from "../test/agents";
import { adaSession, fakeAuthApi } from "../test/auth";
import { fakeProjectsApi, hrProject } from "../test/projects";
import { renderStudio } from "../test/render";
import { AUTOSAVE_MS } from "./DraftEditor";

const organisationId = adaSession.organisations[0]?.id ?? "";
const agentPage = `/organisations/${organisationId}/projects/${hrProject.id}/agents/${hrHelper.id}`;
type Draft = typeof defaultDraft;

function setUp(options: Parameters<typeof fakeAgentsApi>[0] = {}) {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  return fakeAgentsApi({ agents: [hrHelper], ...options });
}

async function openEditor() {
  renderStudio(agentPage);
  return screen.findByRole("form", { name: "Draft" }, { timeout: 5000 });
}

function group(name: string) {
  return screen.getByRole("group", { name });
}

/** The Drafts sent to the API. */
function saves(requests: { route: string; body?: unknown }[]) {
  return requests.filter((request) => request.route === "draft").map((request) => request.body as Draft);
}

const saved = () => screen.findByText("All changes saved", {}, { timeout: 5000 });

test("every configuration group is shown with the Draft's settings", async () => {
  setUp();
  await openEditor();

  for (const name of ["Behaviour", "Retrieval", "Experience", "Guardrails"]) expect(group(name)).toBeInTheDocument();
  const behaviour = group("Behaviour");
  expect(await within(behaviour).findByRole("textbox", { name: "System prompt" })).toHaveTextContent("Answer from the handbook.");
  expect(within(behaviour).getByLabelText("Credential")).toHaveValue("");
  expect(within(behaviour).getByLabelText("Temperature")).toHaveValue(0.7);
  expect(within(behaviour).getByLabelText("Max output tokens")).toHaveValue(1024);
  expect(within(behaviour).getByLabelText("Remembered turns")).toHaveValue(5);
  expect(within(behaviour).getByLabelText(/Fallback text/)).toHaveValue("Sorry, I don't know the answer to that.");
  const retrieval = group("Retrieval");
  expect(within(retrieval).getByLabelText("Chunks per answer (top-k)")).toHaveValue(5);
  expect(within(retrieval).getByLabelText(/Hybrid weighting/)).toHaveValue(0.5);
  expect(within(retrieval).getByLabelText(/Minimum relevance/)).toHaveValue(0);
  expect(await within(retrieval).findByRole("checkbox", { name: "HR" })).not.toBeChecked();
  expect(within(retrieval).getByRole("checkbox", { name: "Show citations to Visitors" })).toBeChecked();
  const experience = group("Experience");
  expect(within(experience).getByLabelText("Display name")).toHaveValue("");
  expect(within(experience).getByLabelText(/Rating prompt after/)).toHaveValue(3);
  const guardrails = group("Guardrails");
  expect(within(guardrails).getByLabelText("Input Guardrail mode")).toHaveValue("block");
  expect(
    within(guardrails).getByText(
      "Every message is checked by the built-in classifier. Block mode is enforced; warn, log and the LLM classifier are saved with the Draft and enforced in a later release.",
    ),
  ).toBeInTheDocument();
  expect(screen.getByRole("status", { name: "Draft status" })).toHaveTextContent("All changes saved");
});

test("a change autosaves after a pause, with an indicator", async () => {
  const { requests } = setUp();
  await openEditor();
  const temperature = within(group("Behaviour")).getByLabelText("Temperature");

  await userEvent.clear(temperature);
  await userEvent.type(temperature, "0.2");

  expect(screen.getByRole("status", { name: "Draft status" })).toHaveTextContent("Unsaved changes");
  await saved();
  // Typing "0.2" is one save once the typing pauses, not one per keystroke.
  expect(saves(requests)).toEqual([{ ...hrHelper.draft, behaviour: { ...hrHelper.draft.behaviour, temperature: 0.2 } }]);
});

test("the indicator shows a save in progress", async () => {
  let release: () => void = () => undefined;
  const held = new Promise<void>((resolve) => (release = resolve));
  setUp({ saveDraft: () => held.then(() => undefined) });
  await openEditor();
  await userEvent.type(within(group("Experience")).getByLabelText("Display name"), "Hana");

  expect(await screen.findByText("Saving…", {}, { timeout: 5000 })).toBeInTheDocument();
  release();
  await saved();
});

test("an Editor sets every Behaviour, Experience and Guardrails setting", async () => {
  const { requests } = setUp();
  await openEditor();
  const behaviour = group("Behaviour");
  await userEvent.clear(within(behaviour).getByLabelText("Max output tokens"));
  await userEvent.type(within(behaviour).getByLabelText("Max output tokens"), "600");
  await userEvent.clear(within(behaviour).getByLabelText("Remembered turns"));
  await userEvent.type(within(behaviour).getByLabelText("Remembered turns"), "2");
  await userEvent.clear(within(behaviour).getByLabelText(/Fallback text/));
  await userEvent.type(within(behaviour).getByLabelText(/Fallback text/), "Ask HR.");
  // The system prompt is a markdown editor: its Markdown view edits the markdown itself.
  await within(behaviour).findByRole("textbox", { name: "System prompt" });
  await userEvent.click(within(behaviour).getByRole("button", { name: "Markdown" }));
  const prompt = within(behaviour).getByRole("textbox", { name: "System prompt (Markdown)" });
  await userEvent.clear(prompt);
  await userEvent.type(prompt, "# Role{enter}{enter}Be brief.");
  const experience = group("Experience");
  await userEvent.type(within(experience).getByLabelText("Display name"), "Hana");
  await userEvent.type(within(experience).getByLabelText(/Avatar URL/), "https://cdn.example.com/hana.png");
  await userEvent.type(within(experience).getByLabelText("Greeting"), "Hi!");
  await userEvent.type(within(experience).getByLabelText(/Starter questions/), "How much leave?{enter}{enter}  When is payday?  ");
  await userEvent.type(within(experience).getByLabelText(/"Send" button/), "Ask");
  await userEvent.type(within(experience).getByLabelText(/"Rate this conversation"/), "How did I do?");
  await userEvent.type(within(experience).getByLabelText(/Unavailable message/), "Back soon.");
  await userEvent.clear(within(experience).getByLabelText(/Rating prompt after/));
  await userEvent.type(within(experience).getByLabelText(/Rating prompt after/), "5");
  const guardrails = group("Guardrails");
  await userEvent.selectOptions(within(guardrails).getByLabelText("Input Guardrail mode"), "warn");
  await userEvent.selectOptions(within(guardrails).getByLabelText(/When the classifier errors/), "open");
  await userEvent.clear(within(guardrails).getByLabelText("Refusal text"));
  await userEvent.type(within(guardrails).getByLabelText("Refusal text"), "No.");

  await saved();
  expect(saves(requests).at(-1)).toEqual({
    behaviour: { ...defaultDraft.behaviour, system_prompt: "# Role\n\nBe brief.", max_output_tokens: 600, remembered_turns: 2, fallback_text: "Ask HR." },
    retrieval: defaultDraft.retrieval,
    experience: {
      display_name: "Hana",
      avatar_url: "https://cdn.example.com/hana.png",
      greeting: "Hi!",
      starter_questions: ["How much leave?", "When is payday?"],
      ui_text: { send_button: "Ask", rate_conversation: "How did I do?", unavailable_message: "Back soon." },
      rating_prompt_after: 5,
    },
    guardrails: { ...defaultDraft.guardrails, input_mode: "warn", fail_mode: "open", refusal_text: "No." },
  });

  // Emptied overrides go back to the built-in text.
  await userEvent.clear(within(experience).getByLabelText(/"Send" button/));
  await userEvent.clear(within(experience).getByLabelText(/Avatar URL/));
  await saved();
  const last = saves(requests).at(-1) as Draft;
  expect(last.experience.ui_text.send_button).toBeNull();
  expect(last.experience.avatar_url).toBeNull();
  // The longest test here: it types into every field, so it gets room on a loaded machine.
}, 30_000);

test("an Editor sets the Retrieval settings and Tag scoping", async () => {
  const { requests } = setUp();
  await openEditor();
  const retrieval = group("Retrieval");
  await within(retrieval).findByRole("checkbox", { name: "Pay" });
  await userEvent.clear(within(retrieval).getByLabelText("Chunks per answer (top-k)"));
  await userEvent.type(within(retrieval).getByLabelText("Chunks per answer (top-k)"), "8");
  await userEvent.clear(within(retrieval).getByLabelText(/Hybrid weighting/));
  await userEvent.type(within(retrieval).getByLabelText(/Hybrid weighting/), "0.3");
  await userEvent.clear(within(retrieval).getByLabelText(/Minimum relevance/));
  await userEvent.type(within(retrieval).getByLabelText(/Minimum relevance/), "0.25");
  await userEvent.click(within(retrieval).getByRole("checkbox", { name: "Pay" }));
  await userEvent.click(within(retrieval).getByRole("checkbox", { name: "HR" }));
  await userEvent.click(within(retrieval).getByRole("checkbox", { name: "Show citations to Visitors" }));

  await saved();
  expect((saves(requests).at(-1) as Draft).retrieval).toEqual({
    ...defaultDraft.retrieval,
    top_k: 8,
    hybrid_weight: 0.3,
    min_score: 0.25,
    tag_ids: [payTag.id, hrTag.id],
    citations: false,
  });

  await userEvent.click(within(retrieval).getByRole("checkbox", { name: "Pay" }));
  await saved();
  expect((saves(requests).at(-1) as Draft).retrieval.tag_ids).toEqual([hrTag.id]);
});

test("a Project without Tags says so", async () => {
  setUp({ tags: [] });
  await openEditor();

  expect(await within(group("Retrieval")).findByText(/no Tags yet/)).toBeInTheDocument();
});

test("the model override, reranker and classifier offer only credentials with the right capability", async () => {
  const { requests } = setUp();
  await openEditor();
  const model = within(group("Behaviour")).getByRole("group", { name: "Model override" });
  const reranker = within(group("Retrieval")).getByRole("group", { name: "Reranker" });
  const classifier = within(group("Guardrails")).getByRole("group", { name: "LLM classifier" });
  await within(model).findByRole("option", { name: "Claude (Anthropic)" });

  const names = (picker: HTMLElement) =>
    within(within(picker).getByLabelText("Credential"))
      .getAllByRole("option")
      .map((option) => option.textContent);
  expect(names(model)).toEqual(["None: use the Default Model", "Claude (Anthropic)", "OpenAI (OpenAI)"]);
  expect(names(reranker)).toEqual(["None", "Voyage (Voyage AI)"]);
  expect(names(classifier)).toEqual(["None", "Claude (Anthropic)", "OpenAI (OpenAI)"]);
  expect(within(model).queryByLabelText("Model")).not.toBeInTheDocument();

  await userEvent.selectOptions(within(model).getByLabelText("Credential"), claude.id);
  // Choosing a credential asks for one of its models; nothing is saved until one is chosen.
  expect(await within(model).findByRole("option", { name: "Claude Haiku 4.5" })).toBeInTheDocument();
  expect(within(model).getByLabelText("Model")).toHaveValue("");
  expect(saves(requests)).toEqual([]);
  await userEvent.selectOptions(within(model).getByLabelText("Model"), "claude-haiku-4-5");
  await userEvent.selectOptions(within(reranker).getByLabelText("Credential"), voyage.id);
  await userEvent.selectOptions(await within(reranker).findByLabelText("Model"), "rerank-2.5");
  await userEvent.selectOptions(within(classifier).getByLabelText("Credential"), openAi.id);
  await within(classifier).findByRole("option", { name: "GPT-4.1 mini" });
  await userEvent.selectOptions(within(classifier).getByLabelText("Model"), "gpt-4.1");

  await saved();
  const last = saves(requests).at(-1) as Draft;
  expect(last.behaviour.model).toEqual({ credential_id: claude.id, model: "claude-haiku-4-5" });
  expect(last.retrieval.reranker).toEqual({ credential_id: voyage.id, model: "rerank-2.5" });
  expect(last.guardrails.classifier).toEqual({ credential_id: openAi.id, model: "gpt-4.1" });

  await userEvent.selectOptions(within(model).getByLabelText("Credential"), "");
  await saved();
  expect((saves(requests).at(-1) as Draft).behaviour.model).toBeNull();
});

test("a saved model override is shown, even when no credential offers that capability", async () => {
  const agent = {
    ...hrHelper,
    draft: { ...defaultDraft, behaviour: { ...defaultDraft.behaviour, model: { credential_id: claude.id, model: "claude-haiku-4-5" } } },
  };
  setUp({ agents: [agent], credentials: [claude] });
  await openEditor();

  const model = within(group("Behaviour")).getByRole("group", { name: "Model override" });
  expect(await within(model).findByRole("option", { name: "Claude Haiku 4.5" })).toBeInTheDocument();
  expect(within(model).getByLabelText("Model")).toHaveValue("claude-haiku-4-5");
  const reranker = within(group("Retrieval")).getByRole("group", { name: "Reranker" });
  expect(within(reranker).getByText(/No credential can rerank yet/)).toBeInTheDocument();
});

test("the models of a credential that can't be loaded say so", async () => {
  setUp({ credentials: [{ ...claude, id: "c9000000-0000-4000-8000-000000000009" }] });
  await openEditor();
  const model = within(group("Behaviour")).getByRole("group", { name: "Model override" });
  await within(model).findByRole("option", { name: "Claude (Anthropic)" });

  await userEvent.selectOptions(within(model).getByLabelText("Credential"), "c9000000-0000-4000-8000-000000000009");

  expect(await within(model).findByText("This credential offers no models for this.")).toBeInTheDocument();
});

test("settings the API refuses are marked with its reasons and not saved", async () => {
  setUp({
    saveDraft: (draft) =>
      draft.behaviour.temperature > 1
        ? HttpResponse.json(
            {
              detail: [
                { loc: ["body", "behaviour", "temperature"], msg: "Input should be less than or equal to 1", type: "less_than_equal" },
                { loc: ["body", "retrieval", "tag_ids", 0], msg: "Choose Tags from this Project.", type: "unknown_tag" },
                { loc: ["body", "behaviour", "model", "model"], msg: "OpenAI doesn't offer x for chat.", type: "model_unavailable" },
              ],
            },
            { status: 422 },
          )
        : undefined,
  });
  await openEditor();
  const temperature = within(group("Behaviour")).getByLabelText("Temperature");
  temperature.removeAttribute("max");

  await userEvent.clear(temperature);
  await userEvent.type(temperature, "3");

  expect(await screen.findByText("Not saved: fix the settings marked below.", {}, { timeout: 5000 })).toBeInTheDocument();
  expect(temperature).toHaveAccessibleDescription(/Input should be less than or equal to 1$/);
  expect(temperature).toHaveAttribute("aria-invalid", "true");
  expect(within(group("Retrieval")).getByText("Choose Tags from this Project.")).toBeInTheDocument();
  expect(within(group("Behaviour")).getByText("OpenAI doesn't offer x for chat.")).toBeInTheDocument();

  // Fixing it saves, and the marks go away.
  await userEvent.clear(temperature);
  await userEvent.type(temperature, "1");
  await saved();
  expect(temperature).not.toHaveAttribute("aria-invalid");
});

test("an empty number is caught before saving", async () => {
  const { requests } = setUp();
  await openEditor();
  const topK = within(group("Retrieval")).getByLabelText("Chunks per answer (top-k)");

  await userEvent.clear(topK);

  expect(await screen.findByText("Not saved: fix the settings marked below.", {}, { timeout: 5000 })).toBeInTheDocument();
  expect(topK).toHaveAccessibleDescription("Enter a number.");
  expect(saves(requests)).toEqual([]);
});

test("a failed save says so, and the next change tries again", async () => {
  let fail = true;
  setUp({ saveDraft: () => (fail ? HttpResponse.json({}, { status: 500 }) : undefined) });
  await openEditor();
  const name = within(group("Experience")).getByLabelText("Display name");

  await userEvent.type(name, "H");
  expect(await screen.findByText("Not saved: something went wrong. Your next change tries again.", {}, { timeout: 5000 })).toBeInTheDocument();

  fail = false;
  await userEvent.type(name, "i");
  await saved();
});

test("a save the network drops says so, and the next change tries again", async () => {
  let drop = true;
  setUp({ saveDraft: () => (drop ? HttpResponse.error() : undefined) });
  await openEditor();
  const name = within(group("Experience")).getByLabelText("Display name");

  await userEvent.type(name, "H");
  expect(await screen.findByText("Not saved: something went wrong. Your next change tries again.", {}, { timeout: 5000 })).toBeInTheDocument();
  expect(name).not.toHaveAttribute("aria-invalid");

  drop = false;
  await userEvent.type(name, "i");
  await saved();
});

test("saves run one at a time, so an older save can't overwrite a newer one", async () => {
  let release: () => void = () => undefined;
  const held = new Promise<void>((resolve) => (release = resolve));
  let calls = 0;
  const { requests } = setUp({ saveDraft: () => (++calls === 1 ? held.then(() => undefined) : undefined) });
  await openEditor();
  const name = within(group("Experience")).getByLabelText("Display name");
  await userEvent.type(name, "H");
  await screen.findByText("Saving…", {}, { timeout: 5000 });

  await userEvent.type(name, "i");
  await new Promise((resolve) => setTimeout(resolve, AUTOSAVE_MS * 2));
  // The newer Draft waits for the older save to finish instead of racing it.
  expect(saves(requests).map((draft) => draft.experience.display_name)).toEqual(["H"]);
  expect(screen.getByRole("status", { name: "Draft status" })).not.toHaveTextContent("All changes saved");
  // A change queued behind "Hi" replaces it: only the newest waiting Draft is sent.
  await userEvent.type(name, "!");
  await new Promise((resolve) => setTimeout(resolve, AUTOSAVE_MS * 2));

  release();
  await saved();
  expect(saves(requests).map((draft) => draft.experience.display_name)).toEqual(["H", "Hi!"]);
});

test("a credential chosen without a model is an unsaved change, not a saved one", async () => {
  const { requests } = setUp();
  await openEditor();
  const model = within(group("Behaviour")).getByRole("group", { name: "Model override" });
  await within(model).findByRole("option", { name: "Claude (Anthropic)" });

  await userEvent.selectOptions(within(model).getByLabelText("Credential"), claude.id);

  const status = screen.getByRole("status", { name: "Draft status" });
  expect(status).toHaveTextContent("Unsaved changes: choose a model.");
  expect(await within(model).findByText("Choose a model to use this credential.")).toBeInTheDocument();
  expect(saves(requests)).toEqual([]);

  await userEvent.selectOptions(within(model).getByLabelText("Model"), "claude-haiku-4-5");
  await saved();
  expect(within(model).queryByText("Choose a model to use this credential.")).not.toBeInTheDocument();
});

test("an archived Project's Draft can't be changed", async () => {
  const detail = "This Project is archived. An Owner can restore it.";
  setUp({ saveDraft: () => HttpResponse.json({ detail }, { status: 409 }) });
  await openEditor();

  await userEvent.type(within(group("Experience")).getByLabelText("Greeting"), "Hi");

  expect(await screen.findByText(`Not saved: ${detail}`, {}, { timeout: 5000 })).toBeInTheDocument();
});

test("a change still waiting to be saved is saved when the Editor leaves the page", async () => {
  const { requests } = setUp();
  await openEditor();

  // Change and leave in the same tick, so the autosave timer can't fire first however slow the machine.
  fireEvent.change(within(group("Experience")).getByLabelText("Greeting"), { target: { value: "Hi" } });
  fireEvent.click(screen.getByRole("link", { name: "All Agents" }));

  await screen.findByRole("heading", { name: "Agents" }, { timeout: 5000 });
  await vi.waitFor(() => {
    expect(saves(requests).map((draft) => draft.experience.greeting)).toEqual(["Hi"]);
  });
});

test.each([
  ["succeeds", () => undefined],
  ["fails", () => HttpResponse.json({}, { status: 500 })],
])("a save that %s after a newer change doesn't decide the status", async (_, outcome) => {
  let release: () => void = () => undefined;
  const held = new Promise<void>((resolve) => (release = resolve));
  let calls = 0;
  const { requests } = setUp({ saveDraft: () => (++calls === 1 ? held.then(outcome) : undefined) });
  await openEditor();
  const name = within(group("Experience")).getByLabelText("Display name");
  await userEvent.type(name, "H");
  await screen.findByText("Saving…", {}, { timeout: 5000 });

  await userEvent.type(name, "i");
  release();

  await saved();
  expect(saves(requests).map((draft) => draft.experience.display_name)).toEqual(["H", "Hi"]);
});
