import type { Schemas } from "@studio/api-client";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi, type Session } from "../test/auth";
import { fakeProjectsApi, hrProject, type Project, salesProject } from "../test/projects";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const projectPage = (projectId: string) => `/organisations/${organisationId}/projects/${projectId}`;
const editorSession: Session = {
  ...adaSession,
  organisations: adaSession.organisations.map((organisation) => ({ ...organisation, role: "editor" as const })),
};
const VOYAGE_CREDENTIAL = "5b0e6c1a-8f3e-4d8a-9c55-0d6f1c2b3a01";
const HAS_DOCUMENTS = "The Embedding Model can't be changed while the Project has Documents. Delete its Documents first.";

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

/** The Embedding Model routes, answering like the API and recording each choice. */
function fakeEmbeddingApi(answer?: () => Response | Promise<Response>) {
  const chosen: unknown[] = [];
  server.use(
    http.get("*/api/organisations/:organisationId/embedding-models", () => HttpResponse.json(choices)),
    http.put("*/api/organisations/:organisationId/projects/:projectId/embedding-model", async ({ request }) => {
      const body = (await request.json()) as Schemas["SetEmbeddingModelRequest"];
      chosen.push(body);
      if (answer) return answer();
      const project: Project = { ...salesProject, embedding_model_id: body.model_id, embedding_credential_id: body.credential_id ?? null };
      return HttpResponse.json(project);
    }),
  );
  return { chosen };
}

test("an Editor chooses a provider Embedding Model for a Project without Documents", async () => {
  fakeAuthApi({ signedInAs: editorSession });
  fakeProjectsApi();
  const { chosen } = fakeEmbeddingApi();
  renderStudio(projectPage(salesProject.id));
  const setting = await screen.findByRole("region", { name: "Embedding Model" });
  expect(setting).toHaveTextContent("Documents are embedded with multilingual-e5-small.");

  await userEvent.click(within(setting).getByRole("button", { name: "Change Embedding Model" }));
  const form = await within(setting).findByRole("form", { name: "Choose the Embedding Model" });
  const select = within(form).getByLabelText("Embedding Model");
  expect(within(select).getAllByRole("option").map((option) => option.textContent)).toEqual([
    "multilingual-e5-small (built in)",
    "voyage-3.5 (Voyage production)",
  ]);
  expect(select).toHaveDisplayValue("multilingual-e5-small (built in)");
  await userEvent.selectOptions(select, "voyage-3.5 (Voyage production)");
  await userEvent.click(within(form).getByRole("button", { name: "Use this model" }));

  expect(await within(setting).findByText("voyage-3.5")).toBeInTheDocument();
  expect(within(setting).queryByRole("form")).not.toBeInTheDocument();
  expect(chosen).toEqual([{ model_id: "voyage-3.5", credential_id: VOYAGE_CREDENTIAL }]);

  // Back to the built-in model, which takes no credential.
  await userEvent.click(within(setting).getByRole("button", { name: "Change Embedding Model" }));
  const again = await within(setting).findByRole("form", { name: "Choose the Embedding Model" });
  expect(within(again).getByLabelText("Embedding Model")).toHaveDisplayValue("voyage-3.5 (Voyage production)");
  await userEvent.selectOptions(within(again).getByLabelText("Embedding Model"), "multilingual-e5-small (built in)");
  await userEvent.click(within(again).getByRole("button", { name: "Use this model" }));
  expect(await within(setting).findByText("multilingual-e5-small")).toBeInTheDocument();
  expect(chosen).toEqual([
    { model_id: "voyage-3.5", credential_id: VOYAGE_CREDENTIAL },
    { model_id: "multilingual-e5-small", credential_id: null },
  ]);
});

test("a Project with Documents keeps its Embedding Model", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  renderStudio(projectPage(hrProject.id));

  const setting = await screen.findByRole("region", { name: "Embedding Model" });

  expect(setting).toHaveTextContent(
    "Documents are embedded with multilingual-e5-small. It can't be changed while the Project has Documents.",
  );
  expect(within(setting).queryByRole("button")).not.toBeInTheDocument();
});

test("choosing can be cancelled, and a refused choice shows the API's reason", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeEmbeddingApi(async () => {
    await delay(200);
    return HttpResponse.json({ detail: HAS_DOCUMENTS }, { status: 409 });
  });
  renderStudio(projectPage(salesProject.id));
  const setting = await screen.findByRole("region", { name: "Embedding Model" });
  await userEvent.click(within(setting).getByRole("button", { name: "Change Embedding Model" }));
  await within(setting).findByRole("form", { name: "Choose the Embedding Model" });
  await userEvent.click(within(setting).getByRole("button", { name: "Cancel" }));
  expect(within(setting).queryByRole("form")).not.toBeInTheDocument();

  await userEvent.click(within(setting).getByRole("button", { name: "Change Embedding Model" }));
  await userEvent.click(await within(setting).findByRole("button", { name: "Use this model" }));

  expect(await within(setting).findByRole("button", { name: "Saving…" })).toBeDisabled();
  expect(await within(setting).findByRole("alert")).toHaveTextContent(HAS_DOCUMENTS);
});

test("an unusable choice shows why, and a failure without a reason says to try again", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  let attempt = 0;
  fakeEmbeddingApi(() => {
    attempt += 1;
    if (attempt === 1) return HttpResponse.json({ detail: "This credential can't be used for embeddings." }, { status: 422 });
    if (attempt === 2) return HttpResponse.json({ detail: "Boom" }, { status: 500 });
    return HttpResponse.json({ detail: [{ loc: ["body", "model_id"], msg: "Field required" }] }, { status: 422 });
  });
  renderStudio(projectPage(salesProject.id));
  const setting = await screen.findByRole("region", { name: "Embedding Model" });
  await userEvent.click(within(setting).getByRole("button", { name: "Change Embedding Model" }));

  await userEvent.click(await within(setting).findByRole("button", { name: "Use this model" }));
  expect(await within(setting).findByRole("alert")).toHaveTextContent("This credential can't be used for embeddings.");

  await userEvent.click(within(setting).getByRole("button", { name: "Use this model" }));
  expect(await within(setting).findByText("Something went wrong. Try again.")).toBeInTheDocument();

  // A validation error's detail is a list, not a reason to show.
  await userEvent.click(within(setting).getByRole("button", { name: "Use this model" }));
  await waitFor(() => {
    expect(attempt).toBe(3);
  });
  expect(await within(setting).findByText("Something went wrong. Try again.")).toBeInTheDocument();
});

test("the choices show their loading and error states", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  server.use(
    http.get("*/api/organisations/:organisationId/embedding-models", async () => {
      await delay(50);
      return HttpResponse.json({ detail: "Boom" }, { status: 500 });
    }),
  );
  renderStudio(projectPage(salesProject.id));
  const setting = await screen.findByRole("region", { name: "Embedding Model" });

  await userEvent.click(within(setting).getByRole("button", { name: "Change Embedding Model" }));

  expect(await within(setting).findByText("Loading the Embedding Models…")).toBeInTheDocument();
  expect(await within(setting).findByText("The Embedding Models could not be loaded. Try again shortly.")).toBeInTheDocument();
});
