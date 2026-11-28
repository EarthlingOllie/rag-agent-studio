import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { adaSession, fakeAuthApi } from "../test/auth";
import { callsElevenLabs, fakeCredentialsApi } from "../test/credentials";
import { fakePricesApi } from "../test/models";
import { renderStudio } from "../test/render";

const organisationId = adaSession.organisations[0]?.id ?? "";
const credentialsPath = `/organisations/${organisationId}/settings/credentials`;
const INVALID_KEY = "ElevenLabs rejected this API key. Check it was copied in full, and that its permissions allow ElevenLabs Agents.";

async function elevenLabsForm() {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio(credentialsPath);
  const form = within(await screen.findByRole("region", { name: "Add a credential" }));
  await userEvent.selectOptions(form.getByLabelText("Provider"), "ElevenLabs");
  return form;
}

function row(name: string) {
  const table = screen.getByRole("table", { name: "Provider Credentials" });
  const found = within(table)
    .getAllByRole("row")
    .find((candidate) => within(candidate).queryByText(name));
  return within(found as HTMLElement)
    .getAllByRole("cell")
    .slice(0, 5)
    .map((cell) => cell.textContent);
}

test("an Owner adds an ElevenLabs credential, used for voice", async () => {
  const api = fakeCredentialsApi({ credentials: [] });
  const form = await elevenLabsForm();

  expect(within(form.getByRole("group", { name: "Use for" })).getAllByRole("checkbox")).toHaveLength(1);
  expect(form.getByLabelText("Voice")).toBeChecked();
  expect(form.getByText(/permissions must allow ElevenLabs Agents/)).toBeInTheDocument();
  await userEvent.type(form.getByLabelText("Name"), "Calls ElevenLabs");
  await userEvent.type(form.getByLabelText("API key"), "sk_example_elevenlabs_e1ev");
  expect(form.getByLabelText("API key")).toHaveAttribute("type", "password");
  await userEvent.click(form.getByRole("button", { name: "Check and save" }));

  expect(await screen.findByText("Calls ElevenLabs was checked and saved.")).toBeInTheDocument();
  expect(api.added).toEqual([
    { name: "Calls ElevenLabs", provider: "elevenlabs", api_key: "sk_example_elevenlabs_e1ev", capabilities: ["voice"] },
  ]);
  expect(await screen.findByLabelText("Key ending e1ev")).toBeInTheDocument();
  expect(row("Calls ElevenLabs")).toEqual(["Calls ElevenLabs", "ElevenLabs", "Voice", "••••e1ev", "Working"]);
});

test("the voice hint is only for ElevenLabs", async () => {
  fakeCredentialsApi({ credentials: [] });
  const form = await elevenLabsForm();

  await userEvent.selectOptions(form.getByLabelText("Provider"), "OpenAI");

  expect(form.queryByText(/ElevenLabs Agents/)).not.toBeInTheDocument();
  expect(form.queryByLabelText("Voice")).not.toBeInTheDocument();
});

test.each([
  ["invalid_key", `The check failed. ${INVALID_KEY}`],
  ["quota_exceeded", "The check failed. The provider says this key is over its rate limit or quota. Try again later, or check your plan."],
  ["provider_unreachable", "The check failed. We couldn't reach the provider to check the key. Try again in a few minutes."],
])("a failed ElevenLabs check on adding shows why (%s)", async (reason, message) => {
  fakeCredentialsApi({ credentials: [] });
  const form = await elevenLabsForm();
  await userEvent.type(form.getByLabelText("Name"), "Broken");
  await userEvent.type(form.getByLabelText("API key"), `fail-${reason}-key`);

  await userEvent.click(form.getByRole("button", { name: "Check and save" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(message);
  expect(screen.getByText("No credentials yet.")).toBeInTheDocument();
});

test("an ElevenLabs credential is re-checked and rotated like any other", async () => {
  const api = fakeCredentialsApi({ credentials: [callsElevenLabs], recheck: "invalid_key" });
  fakePricesApi();
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio(credentialsPath);
  await screen.findByRole("table", { name: "Provider Credentials" });

  await userEvent.click(screen.getByRole("button", { name: "Check now: Calls ElevenLabs" }));
  expect(await screen.findByText(INVALID_KEY)).toBeInTheDocument();
  expect(row("Calls ElevenLabs")[4]).toBe(`Check failed ${INVALID_KEY}`);

  await userEvent.click(screen.getByRole("button", { name: "Rotate key: Calls ElevenLabs" }));
  const newKey = screen.getByLabelText("New API key for Calls ElevenLabs");
  await userEvent.type(newKey, "fail-invalid_key-new");
  await userEvent.click(screen.getByRole("button", { name: "Check and rotate" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(`The check failed. ${INVALID_KEY}`);
  await userEvent.clear(newKey);
  await userEvent.type(newKey, "sk_rotated_elevenlabs_n3wk");
  await userEvent.click(screen.getByRole("button", { name: "Check and rotate" }));

  expect(await screen.findByText("The key of Calls ElevenLabs was checked and replaced.")).toBeInTheDocument();
  expect(api.checked).toEqual([callsElevenLabs.id]);
  expect(api.rotated).toEqual([
    { id: callsElevenLabs.id, apiKey: "fail-invalid_key-new" },
    { id: callsElevenLabs.id, apiKey: "sk_rotated_elevenlabs_n3wk" },
  ]);
  expect(await screen.findByLabelText("Key ending n3wk")).toBeInTheDocument();
});
