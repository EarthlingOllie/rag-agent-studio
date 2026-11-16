import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import { defaultDraft, fakeAgentsApi, hrHelper } from "../test/agents";
import { hrProject } from "../test/projects";
import { type Agent, StaleDraftError, useSaveDraft } from "./agents";
import { DraftConflict } from "./DraftConflict";

const organisationId = "0rg00000-0000-4000-8000-000000000001";
type Draft = typeof defaultDraft;

const prompted = (system_prompt: string): Draft => ({ ...defaultDraft, behaviour: { ...defaultDraft.behaviour, system_prompt } });

/**
 * Another flow that writes to the Draft: it saves a Draft made on the revision it was opened on,
 * and shows the shared prompt when someone else saved first.
 */
function WritesTheDraft({ mine }: { mine: Draft }) {
  const save = useSaveDraft(organisationId, hrProject.id, hrHelper.id);
  const [conflict, setConflict] = useState<Agent | null>(null);
  const [outcome, setOutcome] = useState("");
  const write = (baseRevision: number) => {
    setConflict(null);
    save.mutate(
      { draft: mine, baseRevision },
      {
        onSuccess: (agent) => {
          setOutcome(`Saved: ${agent.draft.behaviour.system_prompt}`);
        },
        onError: (error) => {
          if (error instanceof StaleDraftError) setConflict(error.latest);
        },
      },
    );
  };
  return (
    <>
      <button type="button" onClick={() => {
        write(hrHelper.draft_revision);
      }}>
        Write
      </button>
      {conflict && (
        <DraftConflict
          latest={conflict}
          onLoad={(latest) => {
            setConflict(null);
            setOutcome(`Loaded: ${latest.draft.behaviour.system_prompt}`);
          }}
          onOverwrite={(latest) => {
            write(latest.draft_revision);
          }}
        />
      )}
      <p>{outcome}</p>
    </>
  );
}

function setUp() {
  const api = fakeAgentsApi({ agents: [hrHelper] });
  api.colleagueSaves(hrHelper.id, prompted("Colleague's edit"));
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <WritesTheDraft mine={prompted("Mine")} />
    </QueryClientProvider>,
  );
  return api;
}

async function refused() {
  await userEvent.click(screen.getByRole("button", { name: "Write" }));
  return screen.findByRole("alert");
}

test("a write refused because someone else saved first says when they saved and offers both choices", async () => {
  setUp();

  const prompt = await refused();

  expect(prompt).toHaveTextContent("Someone else saved this Draft while you were editing");
  expect(prompt).toHaveTextContent(new Date(hrHelper.draft_updated_at).toLocaleString());
  expect(within(prompt).getByRole("button", { name: "Load their changes" })).toBeInTheDocument();
  expect(within(prompt).getByRole("button", { name: "Save mine over theirs" })).toBeInTheDocument();
});

test("loading their changes hands over their Draft and saves nothing more", async () => {
  const { requests } = setUp();
  const prompt = await refused();

  await userEvent.click(within(prompt).getByRole("button", { name: "Load their changes" }));

  expect(await screen.findByText("Loaded: Colleague's edit")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(requests.filter((request) => request.route === "draft")).toHaveLength(1);
});

test("saving mine over theirs writes on their revision and succeeds", async () => {
  const { requests } = setUp();
  const prompt = await refused();

  await userEvent.click(within(prompt).getByRole("button", { name: "Save mine over theirs" }));

  expect(await screen.findByText("Saved: Mine")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(requests.filter((request) => request.route === "draft").map((request) => (request.body as Draft).behaviour.system_prompt)).toEqual([
    "Mine",
    "Mine",
  ]);
});
