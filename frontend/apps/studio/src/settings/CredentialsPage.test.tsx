import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi } from "../test/auth";
import { fakeCredentialsApi, legalVoyage, marketingOpenAi } from "../test/credentials";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const credentialsPath = `/organisations/${organisationId}/settings/credentials`;
const editorSession = { ...adaSession, organisations: adaSession.organisations.map((o) => ({ ...o, role: "editor" as const })) };

function rows() {
  const [, ...body] = within(screen.getByRole("table", { name: "Provider Credentials" })).getAllByRole("row");
  return body.map((row) =>
    within(row)
      .getAllByRole("cell")
      .slice(0, 6)
      .map((cell) => cell.textContent),
  );
}

async function openAsOwner() {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio(credentialsPath);
  await screen.findByRole("table", { name: "Provider Credentials" });
}

async function addForm() {
  return within(await screen.findByRole("region", { name: "Add a credential" }));
}

test("every Member sees the credentials with provider, capabilities, masked key, status and last check", async () => {
  fakeCredentialsApi();
  await openAsOwner();

  expect(rows()).toEqual([
    [
      "Legal Voyage",
      "Voyage AI",
      "Embeddings, Reranking",
      "••••9876",
      "Check failed: The provider says this key is over its rate limit or quota. Try again later, or check your plan.",
      "2026-11-04 17:45 UTC",
    ],
    ["Marketing OpenAI", "OpenAI", "Chat, Embeddings", "••••wxyz", "Working", "2026-11-05 09:00 UTC"],
  ]);
  expect(screen.getByLabelText("Key ending wxyz")).toBeInTheDocument();
});

test("Editors see the credentials but none of the Owner controls", async () => {
  fakeCredentialsApi();
  fakeAuthApi({ signedInAs: editorSession });
  renderStudio(credentialsPath);

  expect(await screen.findByRole("table", { name: "Provider Credentials" })).toBeInTheDocument();
  expect(screen.getByText("Only Owners can add, check, rotate or delete credentials.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Check now: / })).not.toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Add a credential" })).not.toBeInTheDocument();
  expect(screen.getAllByRole("columnheader")).toHaveLength(6);
});

test("the Credentials tab is shown to every Member", async () => {
  fakeCredentialsApi();
  fakeAuthApi({ signedInAs: editorSession });
  renderStudio(`/organisations/${organisationId}/settings`);

  await userEvent.click(await screen.findByRole("link", { name: "Credentials" }));

  expect(await screen.findByRole("heading", { name: "Provider Credentials" })).toBeInTheDocument();
});

test("an Organisation without credentials says so", async () => {
  fakeCredentialsApi({ credentials: [] });
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio(credentialsPath);

  expect(await screen.findByText("No credentials yet.")).toBeInTheDocument();
});

test("the credentials list shows its loading and error states", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeCredentialsApi();
  server.use(
    http.get("*/api/organisations/:organisationId/credentials", async () => {
      await delay(50);
      return new HttpResponse(null, { status: 500 });
    }),
    http.get("*/api/providers", () => new HttpResponse(null, { status: 500 })),
  );
  renderStudio(credentialsPath);

  expect(await screen.findByText("Loading credentials…")).toBeInTheDocument();
  expect(await screen.findByText("The credentials could not be loaded. Try again shortly.")).toBeInTheDocument();
  expect(screen.getByText("The providers could not be loaded. Try again shortly.")).toBeInTheDocument();
});

test("an Owner adds a credential, which is checked and saved", async () => {
  const api = fakeCredentialsApi({ credentials: [] });
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio(credentialsPath);
  const form = await addForm();

  await userEvent.selectOptions(form.getByLabelText("Provider"), "OpenAI");
  expect(form.getByLabelText("Chat")).toBeChecked();
  expect(form.getByLabelText("Embeddings")).toBeChecked();
  await userEvent.type(form.getByLabelText("Name"), "Marketing OpenAI");
  await userEvent.type(form.getByLabelText("API key"), "sk-proj-example-key-abcd");
  expect(form.getByLabelText("API key")).toHaveAttribute("type", "password");
  await userEvent.click(form.getByRole("button", { name: "Check and save" }));

  expect(await screen.findByText("Marketing OpenAI was checked and saved.")).toBeInTheDocument();
  expect(api.added).toEqual([
    { name: "Marketing OpenAI", provider: "openai", api_key: "sk-proj-example-key-abcd", capabilities: ["chat", "embeddings"] },
  ]);
  expect(await screen.findByLabelText("Key ending abcd")).toBeInTheDocument();
  expect(form.getByLabelText("Name")).toHaveValue("");
  expect(form.getByLabelText("API key")).toHaveValue("");
});

test("an Owner limits what a credential is used for", async () => {
  const api = fakeCredentialsApi({ credentials: [] });
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio(credentialsPath);
  const form = await addForm();
  await userEvent.selectOptions(form.getByLabelText("Provider"), "Voyage AI");
  await userEvent.type(form.getByLabelText("Name"), "Reranker");
  await userEvent.type(form.getByLabelText("API key"), "pa-example-key-1234");

  await userEvent.click(form.getByLabelText("Embeddings"));
  await userEvent.click(form.getByLabelText("Reranking"));
  expect(form.getByRole("button", { name: "Check and save" })).toBeDisabled();
  await userEvent.click(form.getByLabelText("Reranking"));
  await userEvent.click(form.getByLabelText("Embeddings"));
  await userEvent.click(form.getByLabelText("Embeddings"));
  await userEvent.click(form.getByRole("button", { name: "Check and save" }));

  await screen.findByText("Reranker was checked and saved.");
  expect(api.added).toEqual([expect.objectContaining({ provider: "voyage", capabilities: ["rerank"] })]);
});

test.each([
  ["invalid_key", "The check failed. The provider rejected this API key. Check it was copied in full."],
  [
    "missing_model_access",
    "The check failed. The key works, but it can't use this provider's models. Check the key's permissions in your provider account.",
  ],
  ["quota_exceeded", "The check failed. The provider says this key is over its rate limit or quota. Try again later, or check your plan."],
  ["provider_unreachable", "The check failed. We couldn't reach the provider to check the key. Try again in a few minutes."],
])("a failed check on adding shows why (%s)", async (reason, message) => {
  fakeCredentialsApi({ credentials: [] });
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio(credentialsPath);
  const form = await addForm();
  await userEvent.type(form.getByLabelText("Name"), "Broken");
  await userEvent.type(form.getByLabelText("API key"), `fail-${reason}-key`);

  await userEvent.click(form.getByRole("button", { name: "Check and save" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(message);
  expect(screen.getByText("No credentials yet.")).toBeInTheDocument();
  // The key stays in the form so it can be corrected.
  expect(form.getByLabelText("API key")).toHaveValue(`fail-${reason}-key`);
});

test("the API's refusals of a name or key are shown as they are", async () => {
  fakeCredentialsApi();
  await openAsOwner();
  const form = await addForm();
  await userEvent.type(form.getByLabelText("Name"), "Marketing OpenAI");
  await userEvent.type(form.getByLabelText("API key"), "sk-ant-example-key");
  await userEvent.click(form.getByRole("button", { name: "Check and save" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Another credential in this Organisation already has that name.");

  server.use(
    http.post("*/api/organisations/:organisationId/credentials", () =>
      HttpResponse.json({ detail: "An API key is 8 to 512 characters, with no spaces or line breaks." }, { status: 422 }),
    ),
  );
  await userEvent.click(form.getByRole("button", { name: "Check and save" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("An API key is 8 to 512 characters, with no spaces or line breaks.");

  server.use(
    http.post("*/api/organisations/:organisationId/credentials", () =>
      HttpResponse.json({ detail: [{ msg: "Field required" }] }, { status: 422 }),
    ),
  );
  await userEvent.click(form.getByRole("button", { name: "Check and save" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});

test("the add button says the key is being checked while it is", async () => {
  fakeCredentialsApi({ credentials: [] });
  fakeAuthApi({ signedInAs: adaSession });
  server.use(
    http.post("*/api/organisations/:organisationId/credentials", async () => {
      await delay(50);
      return HttpResponse.json(marketingOpenAi, { status: 201 });
    }),
  );
  renderStudio(credentialsPath);
  const form = await addForm();
  await userEvent.type(form.getByLabelText("Name"), "Slow");
  await userEvent.type(form.getByLabelText("API key"), "sk-ant-example-key");

  await userEvent.click(form.getByRole("button", { name: "Check and save" }));

  expect(await form.findByRole("button", { name: "Checking with the provider…" })).toBeDisabled();
  expect(await screen.findByText("Marketing OpenAI was checked and saved.")).toBeInTheDocument();
});

test("an Owner re-checks a credential on demand", async () => {
  const api = fakeCredentialsApi();
  await openAsOwner();

  await userEvent.click(screen.getByRole("button", { name: "Check now: Legal Voyage" }));

  expect(await screen.findByText("Legal Voyage passed its check.")).toBeInTheDocument();
  expect(api.checked).toEqual([legalVoyage.id]);
  expect(rows()[0]).toEqual(["Legal Voyage", "Voyage AI", "Embeddings, Reranking", "••••9876", "Working", "2026-11-05 12:00 UTC"]);
});

test("a re-check that fails shows the reason on the credential", async () => {
  fakeCredentialsApi({ recheck: "invalid_key" });
  await openAsOwner();

  await userEvent.click(screen.getByRole("button", { name: "Check now: Marketing OpenAI" }));

  expect(
    await screen.findByText("Check failed: The provider rejected this API key. Check it was copied in full."),
  ).toBeInTheDocument();
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});

test("a re-check the API refuses says something went wrong", async () => {
  fakeCredentialsApi();
  server.use(http.post("*/api/organisations/:organisationId/credentials/:credentialId/check", () => new HttpResponse(null, { status: 500 })));
  await openAsOwner();

  await userEvent.click(screen.getByRole("button", { name: "Check now: Marketing OpenAI" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});

test("an Owner rotates a key and the credential keeps its place", async () => {
  const api = fakeCredentialsApi();
  await openAsOwner();

  await userEvent.click(screen.getByRole("button", { name: "Rotate key: Marketing OpenAI" }));
  await userEvent.type(screen.getByLabelText("New API key for Marketing OpenAI"), "sk-proj-rotated-n3w1");
  await userEvent.click(screen.getByRole("button", { name: "Check and rotate" }));

  expect(await screen.findByText("The key of Marketing OpenAI was checked and replaced.")).toBeInTheDocument();
  expect(api.rotated).toEqual([{ id: marketingOpenAi.id, apiKey: "sk-proj-rotated-n3w1" }]);
  expect(await screen.findByLabelText("Key ending n3w1")).toBeInTheDocument();
  expect(screen.queryByLabelText("New API key for Marketing OpenAI")).not.toBeInTheDocument();
});

test("a rotation that fails its check keeps the form open and says why", async () => {
  fakeCredentialsApi();
  await openAsOwner();
  await userEvent.click(screen.getByRole("button", { name: "Rotate key: Marketing OpenAI" }));
  await userEvent.type(screen.getByLabelText("New API key for Marketing OpenAI"), "fail-invalid_key-new");

  await userEvent.click(screen.getByRole("button", { name: "Check and rotate" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("The check failed. The provider rejected this API key.");
  expect(screen.getByLabelText("Key ending wxyz")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByLabelText("New API key for Marketing OpenAI")).not.toBeInTheDocument();
});

test("an Owner deletes an unused credential after confirming", async () => {
  const api = fakeCredentialsApi();
  await openAsOwner();

  await userEvent.click(screen.getByRole("button", { name: "Delete: Legal Voyage" }));
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(api.deleted).toEqual([]);
  await userEvent.click(screen.getByRole("button", { name: "Delete: Legal Voyage" }));
  await userEvent.click(screen.getByRole("button", { name: "Yes, delete Legal Voyage" }));

  expect(await screen.findByText("Legal Voyage was deleted.")).toBeInTheDocument();
  expect(api.deleted).toEqual([legalVoyage.id]);
  expect(rows().map((row) => row[0])).toEqual(["Marketing OpenAI"]);
});

test("deleting a credential still in use is refused with the list of what uses it", async () => {
  fakeCredentialsApi({
    references: {
      [marketingOpenAi.id]: [
        { kind: "agent", id: "a-1", name: "Sales bot" },
        { kind: "project", id: "p-1", name: "Handbook" },
        { kind: "guardrail", id: "g-1", name: "Classifier" },
      ],
    },
  });
  await openAsOwner();

  await userEvent.click(screen.getByRole("button", { name: "Delete: Marketing OpenAI" }));
  await userEvent.click(screen.getByRole("button", { name: "Yes, delete Marketing OpenAI" }));

  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("Marketing OpenAI is still in use, so it wasn't deleted.");
  expect(within(alert).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
    "Agent Sales bot",
    "Project Handbook",
    "guardrail Classifier",
  ]);
  expect(rows().map((row) => row[0])).toEqual(["Legal Voyage", "Marketing OpenAI"]);
});

test("deleting the last credential says so and shows the empty list", async () => {
  fakeCredentialsApi({ credentials: [marketingOpenAi] });
  await openAsOwner();

  await userEvent.click(screen.getByRole("button", { name: "Delete: Marketing OpenAI" }));
  await userEvent.click(screen.getByRole("button", { name: "Yes, delete Marketing OpenAI" }));

  expect(await screen.findByText("Marketing OpenAI was deleted.")).toBeInTheDocument();
  expect(await screen.findByText("No credentials yet.")).toBeInTheDocument();
});
