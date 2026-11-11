import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";

import { agentVersion, defaultDraft, fakeAgentsApi, hrHelper } from "../test/agents";
import { adaSession, fakeAuthApi } from "../test/auth";
import { fakeProjectsApi, hrProject } from "../test/projects";
import { renderStudio } from "../test/render";

const organisationId = adaSession.organisations[0]?.id ?? "";
const agentPage = `/organisations/${organisationId}/projects/${hrProject.id}/agents/${hrHelper.id}`;
type Draft = typeof defaultDraft;

const TRADE_OFF =
  "Agentic lets the model search the Knowledge Base as often as a question needs, which is more accurate and can cost more per reply; Automatic searches once per question, which is cheaper and predictable.";

const agentic: Draft = { ...defaultDraft, retrieval: { ...defaultDraft.retrieval, mode: "agentic", search_limit: 3 } };

function setUp(options: Parameters<typeof fakeAgentsApi>[0] = {}) {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  return fakeAgentsApi({ agents: [hrHelper], ...options });
}

async function openRetrieval() {
  renderStudio(agentPage);
  await screen.findByRole("form", { name: "Draft" }, { timeout: 5000 });
  return screen.getByRole("group", { name: "Retrieval" });
}

function saves(requests: { route: string; body?: unknown }[]) {
  return requests.filter((request) => request.route === "draft").map((request) => request.body as Draft);
}

const saved = () => screen.findByText("All changes saved", {}, { timeout: 5000 });
const searchLimit = (retrieval: HTMLElement) => within(retrieval).queryByLabelText("Search limit");

test("the Retrieval section chooses the Retrieval Mode, explaining the trade-off", async () => {
  setUp();
  const retrieval = await openRetrieval();

  const mode = within(retrieval).getByRole("radiogroup", { name: "Retrieval mode" });
  expect(within(mode).getByRole("radio", { name: "Automatic" })).toBeChecked();
  expect(within(mode).getByRole("radio", { name: "Agentic" })).not.toBeChecked();
  expect(mode).toHaveAccessibleDescription(TRADE_OFF);
  // The Search limit only applies in Agentic mode.
  expect(searchLimit(retrieval)).not.toBeInTheDocument();
});

test("choosing Agentic autosaves it and shows the Search limit, which autosaves too", async () => {
  const { requests } = setUp();
  const retrieval = await openRetrieval();

  await userEvent.click(within(retrieval).getByRole("radio", { name: "Agentic" }));
  await saved();
  expect(saves(requests).at(-1)?.retrieval).toEqual({ ...defaultDraft.retrieval, mode: "agentic" });
  const limit = searchLimit(retrieval) as HTMLElement;
  expect(limit).toHaveValue(3);
  expect(limit).toHaveAttribute("min", "1");
  expect(limit).toHaveAttribute("max", "5");
  expect(limit).toHaveAccessibleDescription("How many times the model may search in one reply, from 1 to 5.");

  await userEvent.clear(limit);
  await userEvent.type(limit, "5");
  await saved();
  expect(saves(requests).at(-1)?.retrieval).toEqual({ ...defaultDraft.retrieval, mode: "agentic", search_limit: 5 });
  expect(screen.getByText("Agentic, up to 5 searches · top-5 · hybrid 0.5")).toBeInTheDocument();

  // Back to Automatic: the Search limit is hidden and kept for next time.
  await userEvent.click(within(retrieval).getByRole("radio", { name: "Automatic" }));
  await saved();
  expect(saves(requests).at(-1)?.retrieval).toEqual({ ...defaultDraft.retrieval, mode: "automatic", search_limit: 5 });
  expect(searchLimit(retrieval)).not.toBeInTheDocument();
  expect(screen.getByText("Automatic · top-5 · hybrid 0.5")).toBeInTheDocument();
});

test.each([
  ["6", "Enter a whole number from 1 to 5."],
  ["0", "Enter a whole number from 1 to 5."],
  ["2.5", "Enter a whole number from 1 to 5."],
  ["", "Enter a number."],
])("a Search limit of %j is caught before saving", async (typed, message) => {
  const { requests } = setUp({ agents: [{ ...hrHelper, draft: agentic }] });
  const retrieval = await openRetrieval();
  const limit = searchLimit(retrieval) as HTMLElement;

  await userEvent.clear(limit);
  if (typed) await userEvent.type(limit, typed);

  expect(await screen.findByText("Not saved: fix the settings marked below.", {}, { timeout: 5000 })).toBeInTheDocument();
  expect(limit).toHaveAccessibleDescription(`How many times the model may search in one reply, from 1 to 5. ${message}`);
  expect(limit).toHaveAttribute("aria-invalid", "true");
  expect(saves(requests)).toEqual([]);
});

test("the server's refusal of the Search limit is shown on the field", async () => {
  setUp({
    agents: [{ ...hrHelper, draft: agentic }],
    saveDraft: () =>
      HttpResponse.json(
        { detail: [{ loc: ["body", "retrieval", "search_limit"], msg: "Input should be less than or equal to 5", type: "less_than_equal" }] },
        { status: 422 },
      ),
  });
  const retrieval = await openRetrieval();
  const limit = searchLimit(retrieval) as HTMLElement;

  await userEvent.clear(limit);
  await userEvent.type(limit, "4");

  expect(await screen.findByText("Not saved: fix the settings marked below.", {}, { timeout: 5000 })).toBeInTheDocument();
  expect(limit).toHaveAccessibleDescription(/Input should be less than or equal to 5$/);
  expect(limit).toHaveAttribute("aria-invalid", "true");
});

test("the server's refusal of the Retrieval Mode is shown on the control", async () => {
  const refusal = "The Default Model can't use tools, so this Agent can't be Agentic. Choose a model that supports Agentic mode.";
  setUp({
    saveDraft: (draft) =>
      draft.retrieval.mode === "agentic"
        ? HttpResponse.json({ detail: [{ loc: ["body", "retrieval", "mode"], msg: refusal, type: "tools_unsupported" }] }, { status: 422 })
        : undefined,
  });
  const retrieval = await openRetrieval();

  await userEvent.click(within(retrieval).getByRole("radio", { name: "Agentic" }));

  expect(await screen.findByText("Not saved: fix the settings marked below.", {}, { timeout: 5000 })).toBeInTheDocument();
  const mode = within(retrieval).getByRole("radiogroup", { name: "Retrieval mode" });
  expect(mode).toHaveAccessibleDescription(`${TRADE_OFF} ${refusal}`);

  await userEvent.click(within(retrieval).getByRole("radio", { name: "Automatic" }));
  await saved();
  expect(mode).toHaveAccessibleDescription(TRADE_OFF);
});

test("an archived Agent's Retrieval Mode can't be changed", async () => {
  setUp({ agents: [{ ...hrHelper, draft: agentic, archived_at: "2026-11-01T09:00:00Z" }] });
  const retrieval = await openRetrieval();

  expect(within(retrieval).getByRole("radio", { name: "Automatic" })).toBeDisabled();
  expect(searchLimit(retrieval)).toBeDisabled();
});

test("Retrieval Mode and Search limit changes read plainly in the Draft's diff", async () => {
  const v1 = agentVersion(1, { config: defaultDraft });
  setUp({
    agents: [{ ...hrHelper, draft: agentic, live_version: { id: v1.id, number: 1 }, has_unpublished_changes: true }],
    versions: { [hrHelper.id]: [v1] },
    diff: () => ({
      from: { kind: "version", version: { id: v1.id, number: 1 } },
      to: { kind: "draft", version: null },
      changes: [
        { path: "retrieval.mode", before: "automatic", after: "agentic", added: null, removed: null, lines: null },
        { path: "retrieval.search_limit", before: 3, after: 5, added: null, removed: null, lines: null },
      ],
      instructions: null,
    }),
  });
  renderStudio(agentPage);
  await screen.findByRole("form", { name: "Draft" }, { timeout: 5000 });

  await userEvent.click(within(screen.getByRole("banner")).getByRole("button", { name: "Publish" }));
  const changes = await screen.findByRole("list", { name: "Changes from v1 to the Draft" }, { timeout: 5000 });
  const items = [...changes.children] as HTMLElement[];
  expect(items.map((item) => item.textContent)).toEqual(["Retrieval › Retrieval modeAutomatic → Agentic", "Retrieval › Search limit3 → 5"]);
});

test("a Search limit left unfinished goes back to 3 when the Agent is made Automatic", async () => {
  const { requests } = setUp({ agents: [{ ...hrHelper, draft: agentic }] });
  const retrieval = await openRetrieval();
  await userEvent.clear(searchLimit(retrieval) as HTMLElement);

  await userEvent.click(within(retrieval).getByRole("radio", { name: "Automatic" }));

  await saved();
  expect(saves(requests)).toEqual([{ ...agentic, retrieval: { ...agentic.retrieval, mode: "automatic", search_limit: 3 } }]);
});
