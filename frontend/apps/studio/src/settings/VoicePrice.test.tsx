import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi } from "../test/auth";
import { callsElevenLabs, fakeCredentialsApi, marketingOpenAi } from "../test/credentials";
import { fakeModelsApi, fakePricesApi } from "../test/models";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const credentialsPath = `/organisations/${organisationId}/settings/credentials`;
const modelsPath = `/organisations/${organisationId}/settings/models`;
const editorSession = { ...adaSession, organisations: adaSession.organisations.map((o) => ({ ...o, role: "editor" as const })) };
const CARD = "Per-minute price for Calls ElevenLabs";

function openCredentials(session = adaSession) {
  fakeAuthApi({ signedInAs: session });
  renderStudio(credentialsPath);
}

async function card() {
  return within(await screen.findByRole("region", { name: CARD }));
}

test("the Credentials page shows a voice credential's platform price per Call minute", async () => {
  fakeCredentialsApi({ credentials: [marketingOpenAi, callsElevenLabs] });
  fakePricesApi();
  openCredentials();

  const voice = await card();

  expect(await voice.findByText("$0.10 per Call minute")).toBeInTheDocument();
  expect(voice.getByText("Each Call's Voice Cost is its minutes times the price in effect when it ends.")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Voice prices" })).toBeInTheDocument();
  expect(screen.getByText(/Override a credential's price to match your ElevenLabs plan/)).toBeInTheDocument();
  expect(voice.getByRole("textbox", { name: "Per-minute price (US dollars)" })).toHaveAttribute("placeholder", "Platform: $0.10");
  expect(voice.queryByRole("button", { name: "Use platform price" })).not.toBeInTheDocument();
  // Only voice credentials have one.
  expect(screen.getAllByRole("region", { name: /Per-minute price for/ })).toHaveLength(1);
});

test("an Owner overrides the per-minute price, then goes back to the platform's", async () => {
  fakeCredentialsApi({ credentials: [callsElevenLabs] });
  const api = fakePricesApi();
  openCredentials();
  const voice = await card();
  const price = await voice.findByRole("textbox", { name: "Per-minute price (US dollars)" });

  await userEvent.type(price, " 0.075 ");
  await userEvent.click(voice.getByRole("button", { name: "Save price" }));

  expect(await screen.findByRole("status")).toHaveTextContent("The per-minute price for Calls ElevenLabs was saved.");
  expect(await voice.findByText("$0.075 per Call minute")).toBeInTheDocument();
  expect(voice.getByText("Override (platform $0.10)")).toBeInTheDocument();
  expect(voice.getByRole("textbox", { name: "Per-minute price (US dollars)" })).toHaveValue("0.075");

  await userEvent.click(voice.getByRole("button", { name: "Use platform price" }));

  expect(await voice.findByText("$0.10 per Call minute")).toBeInTheDocument();
  expect(voice.queryByText(/Override/)).not.toBeInTheDocument();
  expect(voice.getByRole("textbox", { name: "Per-minute price (US dollars)" })).toHaveValue("");
  expect(api.voiceOverridden).toEqual([
    { credentialId: callsElevenLabs.id, perMinute: "0.075" },
    { credentialId: callsElevenLabs.id, perMinute: null },
  ]);
});

test.each(["", "-1", "0.1234567", "lots"])("a per-minute price of %j is not sent", async (typed) => {
  fakeCredentialsApi({ credentials: [callsElevenLabs] });
  const api = fakePricesApi();
  openCredentials();
  const voice = await card();
  const price = await voice.findByRole("textbox", { name: "Per-minute price (US dollars)" });

  if (typed) await userEvent.type(price, typed);
  await userEvent.click(voice.getByRole("button", { name: "Save price" }));

  expect(await voice.findByRole("alert")).toHaveTextContent(
    "A per-minute price is an amount in US dollars, like 0.1 or 0.075, with at most six decimal places.",
  );
  expect(api.voiceOverridden).toEqual([]);
});

test("the API's refusal is shown, and the price is saving meanwhile", async () => {
  fakeCredentialsApi({ credentials: [callsElevenLabs] });
  fakePricesApi({ voiceStatus: 500 });
  openCredentials();
  const voice = await card();

  await userEvent.type(await voice.findByRole("textbox", { name: "Per-minute price (US dollars)" }), "0.2");
  await userEvent.click(voice.getByRole("button", { name: "Save price" }));

  expect(await voice.findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
  expect(voice.getByText("$0.10 per Call minute")).toBeInTheDocument();
});

test("an override without a platform price, and no price at all, are explained", async () => {
  fakeCredentialsApi({ credentials: [callsElevenLabs] });
  fakePricesApi({ voice: { [callsElevenLabs.id]: { unit: "per minute", platform: null, override: null, effective: null } } });
  openCredentials();
  const voice = await card();

  expect(await voice.findByText("No per-minute price")).toBeInTheDocument();
  expect(voice.getByText("Calls with this credential have no known Voice Cost until a price is set.")).toBeInTheDocument();
  expect(voice.getByRole("textbox", { name: "Per-minute price (US dollars)" })).toHaveAttribute("placeholder", "No platform price");

  await userEvent.type(voice.getByRole("textbox", { name: "Per-minute price (US dollars)" }), "0.09");
  await userEvent.click(voice.getByRole("button", { name: "Save price" }));

  expect(await voice.findByText("Override")).toBeInTheDocument();
  expect(voice.getByText("$0.09 per Call minute")).toBeInTheDocument();
});

test("Editors see the per-minute price but cannot override it", async () => {
  fakeCredentialsApi({ credentials: [callsElevenLabs] });
  fakePricesApi();
  openCredentials(editorSession);
  const voice = await card();

  expect(await voice.findByText("$0.10 per Call minute")).toBeInTheDocument();
  expect(voice.queryByRole("form")).not.toBeInTheDocument();
  expect(screen.getByText(/Calls are priced per minute, apart from the Cost of their replies. Only Owners can override prices./)).toBeInTheDocument();
});

test("a per-minute price that can't be loaded says so, and without a voice credential there is no voice price", async () => {
  fakeCredentialsApi({ credentials: [callsElevenLabs] });
  server.use(
    http.get("*/api/organisations/:organisationId/credentials/:credentialId/prices", () => HttpResponse.json({ detail: "Down" }, { status: 500 })),
  );
  const { unmount } = (() => {
    fakeAuthApi({ signedInAs: adaSession });
    return renderStudio(credentialsPath);
  })();

  expect(await (await card()).findByText("The per-minute price could not be loaded. Try again shortly.")).toBeInTheDocument();
  unmount();

  fakeCredentialsApi({ credentials: [marketingOpenAi] });
  openCredentials();
  expect(await screen.findByRole("table", { name: "Provider Credentials" })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Voice prices" })).not.toBeInTheDocument();
});

test("the price table shows a voice credential's per-minute price in place of models", async () => {
  fakeModelsApi({ credentials: [callsElevenLabs] });
  fakePricesApi();
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio(modelsPath);

  expect(await (await card()).findByText("$0.10 per Call minute")).toBeInTheDocument();
  expect(screen.queryByText("This credential offers no models.")).not.toBeInTheDocument();
});
