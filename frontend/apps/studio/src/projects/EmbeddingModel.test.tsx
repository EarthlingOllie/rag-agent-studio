import type { Schemas } from "@studio/api-client";
import { configure, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi, type Session } from "../test/auth";
import {
  fakeProjectsApi,
  hrProject,
  type Project,
  salesProject,
} from "../test/projects";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

// The Project page loads lazily; on a loaded machine its first render can take over the default
// one second, so this file waits longer before a `findBy` gives up (vitest isolates each file).
configure({ asyncUtilTimeout: 5000 });

const organisationId = adaSession.organisations[0]?.id ?? "";
// The Embedding Model is set in the Project's Settings section.
const projectPage = (projectId: string) =>
  `/organisations/${organisationId}/projects/${projectId}/settings`;
const editorSession: Session = {
  ...adaSession,
  organisations: adaSession.organisations.map((organisation) => ({
    ...organisation,
    role: "editor" as const,
  })),
};
const VOYAGE_CREDENTIAL = "5b0e6c1a-8f3e-4d8a-9c55-0d6f1c2b3a01";
const ARCHIVED = "This Project is archived. An Owner can restore it.";

const choices: Schemas["EmbeddingModelChoiceOut"][] = [
  {
    model_id: "multilingual-e5-small",
    name: "multilingual-e5-small (built in)",
    provider: "local",
    dimension: 384,
    tokenizer: "intfloat/multilingual-e5-small",
    token_limit: 512,
    credential_id: null,
    credential_name: null,
  },
  {
    model_id: "voyage-3.5",
    name: "voyage-3.5",
    provider: "voyage",
    dimension: 1024,
    tokenizer: "voyageai/voyage-3.5",
    token_limit: 32000,
    credential_id: VOYAGE_CREDENTIAL,
    credential_name: "Voyage production",
  },
];

type ReEmbed = Schemas["ReEmbedOut"];

const idle = (project: Project): Schemas["EmbeddingModelStateOut"] => ({
  model_id: project.embedding_model_id,
  credential_id: project.embedding_credential_id ?? null,
  pending_model_id: null,
  pending_credential_id: null,
  re_embed: null,
});

const reEmbed = (overrides: Partial<ReEmbed>): ReEmbed => ({
  id: "0f6f2f1e-3d4c-4b5a-9e8d-7c6b5a4f3e2d",
  status: "running",
  from_model_id: "multilingual-e5-small",
  model_id: "voyage-3.5",
  credential_id: VOYAGE_CREDENTIAL,
  embedded_chunks: 0,
  total_chunks: 3,
  error_message: null,
  started_at: "2026-11-06T10:00:00Z",
  finished_at: null,
  ...overrides,
});

/**
 * The Embedding Model routes, answering like the API and recording each choice. A Project
 * without Documents switches at once; ``states`` are what reading the Embedding Model answers
 * after a choice, one per read (the last repeats), as a re-embed would progress.
 */
function fakeEmbeddingApi(
  options: {
    answer?: () => Response | Promise<Response>;
    states?: Schemas["EmbeddingModelStateOut"][];
  } = {},
) {
  const chosen: unknown[] = [];
  const states: Record<string, Schemas["EmbeddingModelStateOut"][]> = {};
  server.use(
    http.get("*/api/organisations/:organisationId/embedding-models", () =>
      HttpResponse.json(choices),
    ),
    http.get(
      "*/api/organisations/:organisationId/projects/:projectId/embedding-model",
      ({ params }) => {
        const projectId = params.projectId as string;
        const queue = states[projectId];
        if (!queue)
          return HttpResponse.json(
            idle(projectId === hrProject.id ? hrProject : salesProject),
          );
        return HttpResponse.json(queue.length > 1 ? queue.shift() : queue[0]);
      },
    ),
    http.put(
      "*/api/organisations/:organisationId/projects/:projectId/embedding-model",
      async ({ params, request }) => {
        const body =
          (await request.json()) as Schemas["SetEmbeddingModelRequest"];
        chosen.push(body);
        if (options.answer) return options.answer();
        const projectId = params.projectId as string;
        const base = projectId === hrProject.id ? hrProject : salesProject;
        if (options.states) {
          states[projectId] = [...options.states];
          return HttpResponse.json(base);
        }
        const project: Project = {
          ...base,
          embedding_model_id: body.model_id,
          embedding_credential_id: body.credential_id ?? null,
        };
        states[projectId] = [idle(project)];
        return HttpResponse.json(project);
      },
    ),
  );
  return { chosen };
}

const DIALOG = "Change the Embedding Model";

/** Opens the Embedding Model dialog from the setting's Change button. */
async function openChange(setting: HTMLElement): Promise<HTMLElement> {
  await userEvent.click(
    within(setting).getByRole("button", { name: "Change Embedding Model" }),
  );
  return screen.findByRole("dialog", { name: DIALOG });
}

test("an Editor chooses a provider Embedding Model for a Project without Documents", async () => {
  fakeAuthApi({ signedInAs: editorSession });
  fakeProjectsApi();
  const { chosen } = fakeEmbeddingApi();
  renderStudio(projectPage(salesProject.id));
  const setting = await screen.findByRole("region", {
    name: "Embedding Model",
  });
  expect(setting).toHaveTextContent(
    "Documents are embedded with multilingual-e5-small.",
  );

  const form = await within(await openChange(setting)).findByRole("form", {
    name: "Choose the Embedding Model",
  });
  const select = within(form).getByLabelText("Embedding Model");
  expect(
    within(select)
      .getAllByRole("option")
      .map((option) => option.textContent),
  ).toEqual([
    "multilingual-e5-small (built in)",
    "voyage-3.5 (Voyage production)",
  ]);
  expect(select).toHaveDisplayValue("multilingual-e5-small (built in)");
  await userEvent.selectOptions(select, "voyage-3.5 (Voyage production)");
  await userEvent.click(
    within(form).getByRole("button", { name: "Use this model" }),
  );

  expect(await within(setting).findByText("voyage-3.5")).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(chosen).toEqual([
    { model_id: "voyage-3.5", credential_id: VOYAGE_CREDENTIAL },
  ]);

  // Back to the built-in model, which takes no credential.
  const again = await within(await openChange(setting)).findByRole("form", {
    name: "Choose the Embedding Model",
  });
  expect(within(again).getByLabelText("Embedding Model")).toHaveDisplayValue(
    "voyage-3.5 (Voyage production)",
  );
  await userEvent.selectOptions(
    within(again).getByLabelText("Embedding Model"),
    "multilingual-e5-small (built in)",
  );
  await userEvent.click(
    within(again).getByRole("button", { name: "Use this model" }),
  );
  expect(
    await within(setting).findByText("multilingual-e5-small"),
  ).toBeInTheDocument();
  expect(chosen).toEqual([
    { model_id: "voyage-3.5", credential_id: VOYAGE_CREDENTIAL },
    { model_id: "multilingual-e5-small", credential_id: null },
  ]);
});

test("changing the model of a Project with Documents shows the re-embed's progress until it switches", async () => {
  fakeAuthApi({ signedInAs: editorSession });
  fakeProjectsApi();
  const running = (embedded: number): Schemas["EmbeddingModelStateOut"] => ({
    ...idle(hrProject),
    pending_model_id: "voyage-3.5",
    pending_credential_id: VOYAGE_CREDENTIAL,
    re_embed: reEmbed({ embedded_chunks: embedded }),
  });
  const { chosen } = fakeEmbeddingApi({
    states: [
      running(1),
      running(2),
      {
        ...idle(hrProject),
        model_id: "voyage-3.5",
        credential_id: VOYAGE_CREDENTIAL,
        re_embed: reEmbed({
          status: "completed",
          embedded_chunks: 3,
          finished_at: "2026-11-06T10:01:00Z",
        }),
      },
    ],
  });
  renderStudio(projectPage(hrProject.id));
  const setting = await screen.findByRole("region", {
    name: "Embedding Model",
  });
  expect(setting).toHaveTextContent(
    "Documents are embedded with multilingual-e5-small. Changing it re-embeds every Document in the background; the current model keeps serving until that finishes.",
  );

  const dialog = await openChange(setting);
  expect(within(dialog).getByRole("status")).toHaveTextContent(
    "Every Document in this Project is re-embedded with the new model in the background. The current model keeps serving until that finishes.",
  );
  const form = within(dialog).getByRole("form", {
    name: "Choose the Embedding Model",
  });
  await userEvent.selectOptions(
    within(form).getByLabelText("Embedding Model"),
    "voyage-3.5 (Voyage production)",
  );
  await userEvent.click(
    within(form).getByRole("button", { name: "Use this model" }),
  );

  const status = await within(setting).findByRole("status");
  expect(status).toHaveTextContent(
    "Re-embedding with voyage-3.5: 1 of 3 Chunks. Retrieval uses multilingual-e5-small until it finishes.",
  );
  expect(
    within(status).getByRole("meter", { name: "Re-embedding progress" }),
  ).toHaveAttribute("aria-valuetext", "1 of 3 Chunks");
  expect(setting).toHaveTextContent(
    "Documents are embedded with multilingual-e5-small.",
  );
  expect(setting).not.toHaveTextContent("Changing it re-embeds");
  // The Studio polls while the re-embed runs.
  expect(await within(setting).findByText(/2 of 3 Chunks/)).toBeInTheDocument();
  await waitFor(() => {
    expect(within(setting).queryByRole("status")).not.toBeInTheDocument();
  });
  expect(setting).toHaveTextContent("Documents are embedded with voyage-3.5.");
  expect(chosen).toEqual([
    { model_id: "voyage-3.5", credential_id: VOYAGE_CREDENTIAL },
  ]);
});

test("a failed re-embed shows its error, and the Project keeps its model", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  const error =
    "The Embedding Model's provider didn't respond after 4 attempts. The Project still uses multilingual-e5-small; choose the model again to retry.";
  fakeEmbeddingApi({
    states: [
      {
        ...idle(hrProject),
        re_embed: reEmbed({
          status: "failed",
          embedded_chunks: 1,
          error_message: error,
        }),
      },
    ],
  });
  renderStudio(projectPage(hrProject.id));
  const setting = await screen.findByRole("region", {
    name: "Embedding Model",
  });

  await userEvent.click(
    await within(await openChange(setting)).findByRole("button", {
      name: "Use this model",
    }),
  );

  expect(await within(setting).findByRole("alert")).toHaveTextContent(
    `Re-embedding with voyage-3.5 failed. ${error}`,
  );
  expect(setting).toHaveTextContent(
    "Documents are embedded with multilingual-e5-small.",
  );
  expect(
    within(setting).getByRole("button", { name: "Change Embedding Model" }),
  ).toBeEnabled();
});

test("the dialog for a Project without Documents says the change applies at once; Cancel and Escape close it with focus back on Change", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  const { chosen } = fakeEmbeddingApi();
  renderStudio(projectPage(salesProject.id));
  const setting = await screen.findByRole("region", {
    name: "Embedding Model",
  });
  const change = within(setting).getByRole("button", {
    name: "Change Embedding Model",
  });
  expect(change).toHaveTextContent(/^Change$/);

  let dialog = await openChange(setting);
  expect(dialog).toHaveAccessibleDescription(
    "Embedding Models come from the Organisation's Provider Credentials that can embed. The built-in model needs none.",
  );
  expect(await within(dialog).findByRole("status")).toHaveTextContent(
    "This Project has no Documents yet, so the new model is used at once.",
  );
  expect(
    within(dialog)
      .getAllByRole("button")
      .map((button) => button.textContent),
  ).toEqual(["", "Cancel", "Use this model"]);
  await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(change).toHaveFocus();

  dialog = await openChange(setting);
  await within(dialog).findByLabelText("Embedding Model");
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(change).toHaveFocus();
  expect(chosen).toEqual([]);
});

test("a refused choice shows the API's reason in the dialog, which stays open", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeEmbeddingApi({
    answer: async () => {
      await delay(200);
      return HttpResponse.json({ detail: ARCHIVED }, { status: 409 });
    },
  });
  renderStudio(projectPage(salesProject.id));
  const setting = await screen.findByRole("region", {
    name: "Embedding Model",
  });
  const dialog = await openChange(setting);
  await userEvent.click(
    await within(dialog).findByRole("button", { name: "Use this model" }),
  );

  expect(
    await within(dialog).findByRole("button", { name: "Saving…" }),
  ).toBeDisabled();
  expect(await within(dialog).findByRole("alert")).toHaveTextContent(ARCHIVED);
  expect(screen.getByRole("dialog", { name: DIALOG })).toBeInTheDocument();
});

test("an unusable choice shows why, and a failure without a reason says to try again", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  let attempt = 0;
  fakeEmbeddingApi({
    answer: () => {
      attempt += 1;
      if (attempt === 1)
        return HttpResponse.json(
          { detail: "This credential can't be used for embeddings." },
          { status: 422 },
        );
      if (attempt === 2)
        return HttpResponse.json({ detail: "Boom" }, { status: 500 });
      return HttpResponse.json(
        { detail: [{ loc: ["body", "model_id"], msg: "Field required" }] },
        { status: 422 },
      );
    },
  });
  renderStudio(projectPage(salesProject.id));
  const setting = await screen.findByRole("region", {
    name: "Embedding Model",
  });
  const dialog = await openChange(setting);

  await userEvent.click(
    await within(dialog).findByRole("button", { name: "Use this model" }),
  );
  expect(await within(dialog).findByRole("alert")).toHaveTextContent(
    "This credential can't be used for embeddings.",
  );

  await userEvent.click(
    within(dialog).getByRole("button", { name: "Use this model" }),
  );
  expect(
    await within(dialog).findByText("Something went wrong. Try again."),
  ).toBeInTheDocument();

  // A validation error's detail is a list, not a reason to show.
  await userEvent.click(
    within(dialog).getByRole("button", { name: "Use this model" }),
  );
  await waitFor(() => {
    expect(attempt).toBe(3);
  });
  expect(
    await within(dialog).findByText("Something went wrong. Try again."),
  ).toBeInTheDocument();
});

test("the choices show their loading and error states in the dialog", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  server.use(
    http.get(
      "*/api/organisations/:organisationId/embedding-models",
      async () => {
        await delay(50);
        return HttpResponse.json({ detail: "Boom" }, { status: 500 });
      },
    ),
  );
  renderStudio(projectPage(salesProject.id));
  const setting = await screen.findByRole("region", {
    name: "Embedding Model",
  });

  const dialog = await openChange(setting);

  expect(
    await within(dialog).findByText("Loading the Embedding Models…"),
  ).toBeInTheDocument();
  expect(await within(dialog).findByRole("alert")).toHaveTextContent(
    "The Embedding Models could not be loaded. Try again shortly.",
  );
  expect(
    within(dialog).queryByRole("button", { name: "Use this model" }),
  ).not.toBeInTheDocument();
  await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("if the re-embed state can't be read, the section shows the Project's model", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  let reads = 0;
  server.use(
    http.get(
      "*/api/organisations/:organisationId/projects/:projectId/embedding-model",
      () => {
        reads += 1;
        return HttpResponse.json({ detail: "Boom" }, { status: 500 });
      },
    ),
  );
  renderStudio(projectPage(hrProject.id));

  const setting = await screen.findByRole("region", {
    name: "Embedding Model",
  });

  await waitFor(() => {
    expect(reads).toBeGreaterThan(0);
  });
  expect(setting).toHaveTextContent(
    "Documents are embedded with multilingual-e5-small.",
  );
  expect(within(setting).queryByRole("status")).not.toBeInTheDocument();
  expect(within(setting).queryByRole("alert")).not.toBeInTheDocument();
});
