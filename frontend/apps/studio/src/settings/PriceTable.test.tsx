import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi } from "../test/auth";
import { legalVoyage, marketingOpenAi } from "../test/credentials";
import { fakeModelsApi, fakePricesApi, legalClaude, platformPrices } from "../test/models";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const modelsPath = `/organisations/${organisationId}/settings/models`;
const editorSession = { ...adaSession, organisations: adaSession.organisations.map((o) => ({ ...o, role: "editor" as const })) };

function openAs(session = adaSession) {
  fakeAuthApi({ signedInAs: session });
  renderStudio(modelsPath);
}

async function priceTable(name: string) {
  return screen.findByRole("table", { name: `Prices for ${name}` });
}

/** The Input, Output and Cached input cells of a model's row. */
function rowText(table: HTMLElement, model: string) {
  return Array.from(within(table).getByRole("row", { name: new RegExp(model) }).querySelectorAll("td"))
    .slice(0, 3)
    .map((cell) => cell.textContent);
}

async function overrideForm(model: string) {
  await userEvent.click(await screen.findByRole("button", { name: `Override prices: ${model}` }));
  return within(screen.getByRole("form", { name: `Override prices for ${model}` }));
}

test("every Member sees each model's platform price for the chosen credential", async () => {
  fakeModelsApi();
  openAs(editorSession);

  expect(await screen.findByRole("heading", { name: "Prices" })).toBeInTheDocument();
  // Credentials are offered by name; the first is shown.
  const choice = await screen.findByRole("combobox", { name: "Show prices for" });
  expect(within(choice).getAllByRole("option").map((o) => o.textContent)).toEqual(["Legal Claude", "Marketing OpenAI", "Search OpenAI"]);
  const claude = await priceTable("Legal Claude");
  expect(within(claude).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Model", "Input", "Output", "Cached input"]);
  expect(rowText(claude, "Claude Sonnet 4.5")).toEqual(["$3.00", "$15.00", "$0.30"]);
  expect(rowText(claude, "Claude Haiku 4.5")).toEqual(["$1.00", "$5.00", "$0.10"]);
  expect(screen.getByText(/Only Owners can override prices/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Override prices/ })).not.toBeInTheDocument();

  await userEvent.selectOptions(choice, "Marketing OpenAI");

  const openai = await priceTable("Marketing OpenAI");
  expect(rowText(openai, "GPT-4.1")).toEqual(["$2.00", "$8.00", "$0.50"]);
  expect(rowText(openai, "text-embedding-3-small")).toEqual(["No price", "No price", "No price"]);
});

test("an Owner overrides a model's prices, and the platform price stays visible", async () => {
  fakeModelsApi();
  const api = fakePricesApi();
  openAs();
  const form = await overrideForm("Claude Sonnet 4.5");
  expect(form.getByRole("textbox", { name: "Input" })).toHaveAttribute("placeholder", "Platform: $3.00");

  await userEvent.type(form.getByRole("textbox", { name: "Input" }), "2.5");
  await userEvent.type(form.getByRole("textbox", { name: "Cached input" }), " 0.125 ");
  await userEvent.click(form.getByRole("button", { name: "Save prices" }));

  expect(await screen.findByRole("status")).toHaveTextContent("Prices for Claude Sonnet 4.5 saved.");
  expect(api.overridden).toEqual([
    { credentialId: legalClaude.id, body: { model: "claude-sonnet-4-5", input: "2.5", output: null, cached_input: "0.125" } },
  ]);
  const claude = await priceTable("Legal Claude");
  expect(rowText(claude, "Claude Sonnet 4.5")).toEqual(["$2.50Override (platform $3.00)", "$15.00", "$0.125Override (platform $0.30)"]);
  expect(screen.queryByRole("form", { name: /Override prices for/ })).not.toBeInTheDocument();
});

test("an override is edited from its current prices, and can go back to the platform prices", async () => {
  fakeModelsApi();
  const api = fakePricesApi({
    prices: {
      [legalClaude.id]: platformPrices[legalClaude.id]?.map((row) =>
        row.model === "claude-haiku-4-5"
          ? { ...row, override: { input: null, output: "4", cached_input: null }, effective: { ...row.effective, output: "4" } }
          : row,
      ) ?? [],
    },
  });
  openAs();
  expect(rowText(await priceTable("Legal Claude"), "Claude Haiku 4.5")).toEqual(["$1.00", "$4.00Override (platform $5.00)", "$0.10"]);
  const form = await overrideForm("Claude Haiku 4.5");
  expect(form.getByRole("textbox", { name: "Output" })).toHaveValue("4");

  await userEvent.click(form.getByRole("button", { name: "Use platform prices" }));

  expect(await screen.findByRole("status")).toHaveTextContent("Claude Haiku 4.5 uses the platform prices again.");
  expect(api.overridden.map((o) => o.body)).toEqual([{ model: "claude-haiku-4-5", input: null, output: null, cached_input: null }]);
  expect(rowText(await priceTable("Legal Claude"), "Claude Haiku 4.5")).toEqual(["$1.00", "$5.00", "$0.10"]);
});

test("a model without a platform price can be priced by an override", async () => {
  fakeModelsApi();
  fakePricesApi();
  openAs();
  await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Show prices for" }), "Marketing OpenAI");
  const form = await overrideForm("text-embedding-3-small");
  expect(form.getByRole("textbox", { name: "Input" })).toHaveAttribute("placeholder", "No platform price");
  expect(form.queryByRole("button", { name: "Use platform prices" })).not.toBeInTheDocument();

  await userEvent.type(form.getByRole("textbox", { name: "Input" }), "0.02");
  await userEvent.click(form.getByRole("button", { name: "Save prices" }));

  await screen.findByRole("status");
  expect(rowText(await priceTable("Marketing OpenAI"), "text-embedding-3-small")).toEqual(["$0.02Override", "No price", "No price"]);
});

test.each(["-1", "abc", "1.0000001", "1234567"])("%s is not a price, and is not sent", async (typed) => {
  fakeModelsApi();
  const api = fakePricesApi();
  openAs();
  const form = await overrideForm("Claude Sonnet 4.5");

  await userEvent.type(form.getByRole("textbox", { name: "Output" }), typed);
  await userEvent.click(form.getByRole("button", { name: "Save prices" }));

  expect(await form.findByRole("alert")).toHaveTextContent("Prices are amounts in US dollars per million tokens, like 3 or 0.075");
  expect(api.overridden).toEqual([]);
});

test("the API's refusal is shown", async () => {
  fakeModelsApi();
  server.use(
    http.put("*/api/organisations/:organisationId/credentials/:credentialId/prices", () =>
      HttpResponse.json({ detail: "This credential doesn't offer claude-sonnet-4-5." }, { status: 422 }),
    ),
  );
  openAs();
  const form = await overrideForm("Claude Sonnet 4.5");

  await userEvent.type(form.getByRole("textbox", { name: "Input" }), "1");
  await userEvent.click(form.getByRole("button", { name: "Save prices" }));

  expect(await form.findByRole("alert")).toHaveTextContent("This credential doesn't offer claude-sonnet-4-5.");
  expect(rowText(await priceTable("Legal Claude"), "Claude Sonnet 4.5")).toEqual(["$3.00", "$15.00", "$0.30"]);
});

test("cancelling closes the form without saving", async () => {
  fakeModelsApi();
  const api = fakePricesApi();
  openAs();
  const form = await overrideForm("Claude Sonnet 4.5");
  await userEvent.type(form.getByRole("textbox", { name: "Input" }), "1");

  await userEvent.click(form.getByRole("button", { name: "Cancel" }));

  expect(screen.queryByRole("form", { name: /Override prices for/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  expect(api.overridden).toEqual([]);
});

test("the saving state is shown while an override is saved", async () => {
  fakeModelsApi();
  let release: () => void = () => undefined;
  server.use(
    http.put("*/api/organisations/:organisationId/credentials/:credentialId/prices", async () => {
      await new Promise<void>((resolve) => {
        release = resolve;
      });
      return HttpResponse.json({ detail: "Down" }, { status: 500 });
    }),
  );
  openAs();
  const form = await overrideForm("Claude Sonnet 4.5");
  await userEvent.type(form.getByRole("textbox", { name: "Input" }), "1");

  await userEvent.click(form.getByRole("button", { name: "Save prices" }));

  expect(await form.findByRole("button", { name: "Saving…" })).toBeDisabled();
  release();
  expect(await form.findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});

test("a credential that offers no models says so", async () => {
  fakeModelsApi({ credentials: [legalVoyage] });
  openAs();

  expect(await screen.findByText("This credential offers no models.")).toBeInTheDocument();
});

test("without credentials there is nothing to price", async () => {
  fakeModelsApi({ credentials: [] });
  openAs();

  expect(await screen.findByText("No credentials yet, so there is nothing to price.")).toBeInTheDocument();
});

test("prices that can't be loaded say so", async () => {
  fakeModelsApi({ credentials: [marketingOpenAi] });
  server.use(
    http.get("*/api/organisations/:organisationId/credentials/:credentialId/prices", () => HttpResponse.json({ detail: "Down" }, { status: 500 })),
  );
  openAs();

  expect(await screen.findByText("The prices could not be loaded. Try again shortly.")).toBeInTheDocument();
});

test("credentials that can't be loaded leave the prices unavailable", async () => {
  fakeModelsApi();
  server.use(http.get("*/api/organisations/:organisationId/credentials", () => HttpResponse.json({ detail: "Down" }, { status: 500 })));
  openAs(editorSession);

  expect(await screen.findByText("The prices could not be loaded. Try again shortly.")).toBeInTheDocument();
});
