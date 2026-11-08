import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { DEFAULT_UNAVAILABLE_TEXT, fakeAgentsApi, hrHelper, oldHelper } from "../test/agents";
import { adaSession, fakeAuthApi } from "../test/auth";
import { fakeProjectsApi, hrProject } from "../test/projects";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const agentPage = (agentId: string) =>
  `/organisations/${organisationId}/projects/${hrProject.id}/agents/${agentId}`;
const liveHelper = { ...hrHelper, live_version: { id: "a1e00000-0000-4000-8000-000000000003", number: 3 } };
const snippet = `<script src="${window.location.origin}/embed.js" data-agent="${hrHelper.public_id}" async></script>`;

function setUp(options: Parameters<typeof fakeAgentsApi>[0] = {}) {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  return fakeAgentsApi({ agents: [liveHelper], ...options });
}

async function embedSection() {
  return screen.findByRole("region", { name: "Embed" }, { timeout: 5000 });
}

test("an Agent that has never been published has no Embed Snippet yet", async () => {
  setUp({ agents: [hrHelper] });
  renderStudio(agentPage(hrHelper.id));

  const embed = await embedSection();
  expect(embed).toHaveTextContent("Publish the Agent to get its Embed Snippet.");
  expect(within(embed).queryByRole("button", { name: "Copy snippet" })).not.toBeInTheDocument();
  expect(within(embed).queryByLabelText("Embed Snippet")).not.toBeInTheDocument();
});

test("a live Agent's Embed Snippet is shown and copied", async () => {
  const user = userEvent.setup();
  setUp();
  renderStudio(agentPage(liveHelper.id));

  const embed = await embedSection();
  expect(within(embed).getByLabelText("Embed Snippet")).toHaveTextContent(snippet);
  await user.click(within(embed).getByRole("button", { name: "Copy snippet" }));

  expect(await within(embed).findByText("Copied.")).toBeInTheDocument();
  expect(await navigator.clipboard.readText()).toBe(snippet);
});

test("when the browser refuses to copy, the Editor is told to copy it by hand", async () => {
  const user = userEvent.setup();
  setUp();
  renderStudio(agentPage(liveHelper.id));
  const embed = await embedSection();
  vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("denied"));

  await user.click(within(embed).getByRole("button", { name: "Copy snippet" }));

  expect(await within(embed).findByText("Couldn't copy. Select the snippet and copy it.")).toBeInTheDocument();
});

test("an archived Agent has no Embed section", async () => {
  setUp({ agents: [{ ...oldHelper, live_version: liveHelper.live_version }] });
  renderStudio(agentPage(oldHelper.id));

  expect(await screen.findByRole("heading", { name: oldHelper.name }, { timeout: 5000 })).toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Embed" })).not.toBeInTheDocument();
});

test("an Editor saves the Allowed Origins, one per line", async () => {
  const user = userEvent.setup();
  const { requests } = setUp({ allowedOrigins: ["https://www.example.com"] });
  renderStudio(agentPage(liveHelper.id));
  const embed = await embedSection();
  const field = within(embed).getByLabelText("Allowed Origins");
  expect(await within(embed).findByDisplayValue("https://www.example.com")).toBe(field);

  await user.clear(field);
  await user.type(field, " HTTPS://Shop.example.com/ \n\nhttp://localhost:8080\n");
  await user.click(within(embed).getByRole("button", { name: "Save Allowed Origins" }));

  expect(await within(embed).findByText("Saved. Pages on these sites can show the Agent now.")).toBeInTheDocument();
  expect(field).toHaveValue("https://shop.example.com\nhttp://localhost:8080");
  expect(requests.filter((r) => r.route === "operational-settings")).toEqual([
    {
      route: "operational-settings",
      body: { allowed_origins: ["HTTPS://Shop.example.com/", "http://localhost:8080"] },
    },
  ]);
});

test("an invalid Allowed Origin is explained", async () => {
  const user = userEvent.setup();
  setUp();
  renderStudio(agentPage(liveHelper.id));
  const embed = await embedSection();
  const field = within(embed).getByLabelText("Allowed Origins");
  await waitFor(() => {
    expect(field).toBeEnabled();
  });

  await user.type(field, "www.example.com");
  await user.click(within(embed).getByRole("button", { name: "Save Allowed Origins" }));

  expect(await within(embed).findByRole("alert")).toHaveTextContent(
    "'www.example.com' isn't a site address. Use a scheme, host and optional port, such as https://www.example.com, https://*.example.com for its subdomains, or http://localhost:8080 (http://localhost:* for any port).",
  );
  expect(field).toHaveValue("www.example.com");
});

const settingsPath =
  "*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/operational-settings";

test("a failure to save the Allowed Origins is reported", async () => {
  const user = userEvent.setup();
  setUp({ allowedOrigins: ["https://www.example.com"] });
  server.use(http.patch(settingsPath, () => HttpResponse.json({ detail: "Boom" }, { status: 500 })));
  renderStudio(agentPage(liveHelper.id));
  const embed = await embedSection();
  await within(embed).findByDisplayValue("https://www.example.com");

  await user.click(within(embed).getByRole("button", { name: "Save Allowed Origins" }));

  expect(await within(embed).findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});

test("while the Allowed Origins load, they cannot be saved over", async () => {
  const user = userEvent.setup();
  const { requests } = setUp({ allowedOrigins: ["https://www.example.com"] });
  let puts = 0;
  server.use(
    http.get(settingsPath, () => new Promise<Response>(() => undefined)),
    http.patch(settingsPath, () => {
      puts += 1;
      return HttpResponse.json({ allowed_origins: [], unavailable_text: "" });
    }),
  );
  renderStudio(agentPage(liveHelper.id));
  const embed = await embedSection();
  const save = within(embed).getByRole("button", { name: "Save Allowed Origins" });

  expect(within(embed).getByLabelText("Allowed Origins")).toBeDisabled();
  expect(save).toBeDisabled();
  await user.click(save);
  expect(puts).toBe(0);
  expect(requests.filter((r) => r.route === "operational-settings")).toEqual([]);
});

test("when the Allowed Origins can't be loaded, they cannot be saved over", async () => {
  const user = userEvent.setup();
  setUp({ allowedOrigins: ["https://www.example.com"] });
  let puts = 0;
  server.use(
    http.get(settingsPath, () => HttpResponse.json({ detail: "Not Found" }, { status: 404 })),
    http.patch(settingsPath, () => {
      puts += 1;
      return HttpResponse.json({ allowed_origins: [], unavailable_text: "" });
    }),
  );
  renderStudio(agentPage(liveHelper.id));
  const embed = await embedSection();

  expect(await within(embed).findByText("The Operational Settings could not be loaded.")).toBeInTheDocument();
  const save = within(embed).getByRole("button", { name: "Save Allowed Origins" });
  expect(within(embed).getByLabelText("Allowed Origins")).toBeDisabled();
  expect(save).toBeDisabled();
  await user.click(save);
  expect(puts).toBe(0);
});

test("subdomain wildcards and localhost on any port are saved as Allowed Origins", async () => {
  const user = userEvent.setup();
  const { requests } = setUp();
  renderStudio(agentPage(liveHelper.id));
  const embed = await embedSection();
  const field = within(embed).getByLabelText("Allowed Origins");
  await waitFor(() => {
    expect(field).toBeEnabled();
  });

  await user.type(field, "https://*.Example.com\nhttp://localhost:*");
  await user.click(within(embed).getByRole("button", { name: "Save Allowed Origins" }));

  expect(await within(embed).findByText("Saved. Pages on these sites can show the Agent now.")).toBeInTheDocument();
  expect(field).toHaveValue("https://*.example.com\nhttp://localhost:*");
  expect(requests).toContainEqual({
    route: "operational-settings",
    body: { allowed_origins: ["https://*.Example.com", "http://localhost:*"] },
  });
});

test("an Editor words the unavailable text Visitors see", async () => {
  const user = userEvent.setup();
  const { requests } = setUp({ allowedOrigins: ["https://www.example.com"] });
  renderStudio(agentPage(liveHelper.id));
  const embed = await embedSection();
  const field = within(embed).getByLabelText("Unavailable text");
  expect(await within(embed).findByDisplayValue(DEFAULT_UNAVAILABLE_TEXT)).toBe(field);

  await user.clear(field);
  await user.type(field, "Our helper is having a break. Call us on 0123.");
  await user.click(within(embed).getByRole("button", { name: "Save unavailable text" }));

  expect(await within(embed).findByText("Saved. Visitors see it from their next message.")).toBeInTheDocument();
  expect(requests.filter((r) => r.route === "operational-settings")).toEqual([
    {
      route: "operational-settings",
      body: { unavailable_text: "Our helper is having a break. Call us on 0123." },
    },
  ]);
  // The Allowed Origins are left as they were.
  expect(within(embed).getByLabelText("Allowed Origins")).toHaveValue("https://www.example.com");
});

test("emptying the unavailable text restores the default", async () => {
  const user = userEvent.setup();
  setUp({ unavailableText: "Back soon." });
  renderStudio(agentPage(liveHelper.id));
  const embed = await embedSection();
  const field = await within(embed).findByDisplayValue("Back soon.");

  await user.clear(field);
  await user.click(within(embed).getByRole("button", { name: "Save unavailable text" }));

  expect(await within(embed).findByDisplayValue(DEFAULT_UNAVAILABLE_TEXT)).toBe(field);
});

test("a refused unavailable text is explained", async () => {
  const user = userEvent.setup();
  setUp();
  server.use(
    http.patch(settingsPath, () =>
      HttpResponse.json(
        {
          detail: [
            {
              loc: ["body", "unavailable_text"],
              msg: "String should have at most 500 characters",
              type: "string_too_long",
            },
          ],
        },
        { status: 422 },
      ),
    ),
  );
  renderStudio(agentPage(liveHelper.id));
  const embed = await embedSection();
  await within(embed).findByDisplayValue(DEFAULT_UNAVAILABLE_TEXT);

  await user.click(within(embed).getByRole("button", { name: "Save unavailable text" }));

  expect(await within(embed).findByRole("alert")).toHaveTextContent(
    "String should have at most 500 characters",
  );
});

test("while the Operational Settings load, the unavailable text cannot be saved over", async () => {
  setUp();
  server.use(http.get(settingsPath, () => new Promise<Response>(() => undefined)));
  renderStudio(agentPage(liveHelper.id));
  const embed = await embedSection();

  expect(within(embed).getByLabelText("Unavailable text")).toBeDisabled();
  expect(within(embed).getByRole("button", { name: "Save unavailable text" })).toBeDisabled();
});

test("an Editor sets the rate limits per Conversation and per IP address", async () => {
  const user = userEvent.setup();
  const { requests } = setUp({ unavailableText: "Back soon." });
  renderStudio(agentPage(liveHelper.id));
  const embed = await embedSection();
  const perConversation = within(embed).getByLabelText("Messages per minute per Conversation");
  const perIp = within(embed).getByLabelText("Messages per minute per IP address");
  expect(await within(embed).findByDisplayValue("10")).toBe(perConversation);
  expect(perIp).toHaveValue(30);

  await user.clear(perConversation);
  await user.type(perConversation, "4");
  await user.clear(perIp);
  await user.type(perIp, "12");
  await user.click(within(embed).getByRole("button", { name: "Save rate limits" }));

  expect(
    await within(embed).findByText("Saved. Messages over a limit get the unavailable text from now on."),
  ).toBeInTheDocument();
  expect(requests.filter((r) => r.route === "operational-settings")).toEqual([
    {
      route: "operational-settings",
      body: { conversation_messages_per_minute: 4, ip_messages_per_minute: 12 },
    },
  ]);
  expect(perConversation).toHaveValue(4);
  expect(perIp).toHaveValue(12);
  // The other settings are left as they were.
  expect(within(embed).getByLabelText("Unavailable text")).toHaveValue("Back soon.");
});

test("a refused rate limit is explained", async () => {
  const user = userEvent.setup();
  setUp();
  server.use(
    http.patch(settingsPath, () =>
      HttpResponse.json(
        {
          detail: [
            {
              loc: ["body", "ip_messages_per_minute"],
              msg: "Input should be less than or equal to 10000",
              type: "less_than_equal",
            },
          ],
        },
        { status: 422 },
      ),
    ),
  );
  renderStudio(agentPage(liveHelper.id));
  const embed = await embedSection();
  const perIp = await within(embed).findByDisplayValue("30");

  await user.clear(perIp);
  await user.type(perIp, "20000");
  await user.click(within(embed).getByRole("button", { name: "Save rate limits" }));

  expect(await within(embed).findByRole("alert")).toHaveTextContent("Input should be less than or equal to 10000");
  // Editing again clears the explanation.
  await user.type(perIp, "0");
  expect(within(embed).queryByRole("alert")).not.toBeInTheDocument();
});

test("while the Operational Settings load, the rate limits cannot be saved over", async () => {
  setUp();
  server.use(http.get(settingsPath, () => new Promise<Response>(() => undefined)));
  renderStudio(agentPage(liveHelper.id));
  const embed = await embedSection();

  expect(within(embed).getByLabelText("Messages per minute per Conversation")).toBeDisabled();
  expect(within(embed).getByLabelText("Messages per minute per IP address")).toBeDisabled();
  expect(within(embed).getByRole("button", { name: "Save rate limits" })).toBeDisabled();
});

test("the snippet chooses a bubble or an inline container by its data attributes", async () => {
  const user = userEvent.setup();
  setUp();
  renderStudio(agentPage(liveHelper.id));
  const embed = await embedSection();
  const launcher = within(embed).getByRole("combobox", { name: "Launcher" });
  expect(launcher).toHaveValue("theme");
  expect(within(embed).queryByLabelText("Container selector")).not.toBeInTheDocument();
  const start = `<script src="${window.location.origin}/embed.js" data-agent="${hrHelper.public_id}"`;

  await user.selectOptions(launcher, "bubble");
  expect(within(embed).getByLabelText("Embed Snippet")).toHaveTextContent(`${start} data-launcher="bubble" async></script>`);

  await user.selectOptions(launcher, "inline");
  expect(within(embed).getByLabelText("Embed Snippet")).toHaveTextContent(
    `${start} data-launcher="inline" data-target="#chat" async></script>`,
  );
  const target = within(embed).getByLabelText("Container selector");
  await user.clear(target);
  await user.type(target, '[[data-help="a&b"]');
  expect(within(embed).getByLabelText("Embed Snippet")).toHaveTextContent(
    `${start} data-launcher="inline" data-target="[data-help=&quot;a&amp;b&quot;]" async></script>`,
  );
  await user.click(within(embed).getByRole("button", { name: "Copy snippet" }));
  expect(await navigator.clipboard.readText()).toBe(
    `${start} data-launcher="inline" data-target="[data-help=&quot;a&amp;b&quot;]" async></script>`,
  );

  // Without a selector the widget follows the snippet.
  await user.clear(target);
  expect(within(embed).getByLabelText("Embed Snippet")).toHaveTextContent(`${start} data-launcher="inline" async></script>`);
});

// The Token Budget

const usagePath = "*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/token-usage";

test("the budget meter shows today's usage against the daily Token Budget", async () => {
  setUp({ tokensUsed: 250_000 });
  renderStudio(agentPage(liveHelper.id));
  const embed = await embedSection();

  const meter = await within(embed).findByRole("progressbar", { name: "Tokens used today" });
  await waitFor(() => {
    expect(meter).toHaveAttribute("aria-valuenow", "250000");
  });
  expect(meter).toHaveAttribute("aria-valuemin", "0");
  expect(meter).toHaveAttribute("aria-valuemax", "1000000");
  expect(within(embed).getByText("250,000 of 1,000,000 tokens used today (25%).")).toBeInTheDocument();
  expect(
    within(embed).getByText("The budget resets at midnight UTC. The Playground doesn't count."),
  ).toBeInTheDocument();
  expect(within(embed).queryByText(/Today's Token Budget is spent/)).not.toBeInTheDocument();
});

test("a spent budget is explained beside the meter", async () => {
  setUp({ tokensUsed: 1_000_480 });
  renderStudio(agentPage(liveHelper.id));
  const embed = await embedSection();

  expect(
    await within(embed).findByText(
      "Today's Token Budget is spent: Visitors see the unavailable text until midnight UTC, or until you raise the budget.",
    ),
  ).toBeInTheDocument();
  // The meter stops at full.
  expect(within(embed).getByRole("progressbar", { name: "Tokens used today" })).toHaveAttribute(
    "aria-valuenow",
    "1000000",
  );
  expect(within(embed).getByText("1,000,480 of 1,000,000 tokens used today (100%).")).toBeInTheDocument();
});

test("today's usage that can't be loaded says so", async () => {
  setUp({ tokenUsage: () => HttpResponse.json({ detail: "Boom" }, { status: 500 }) });
  renderStudio(agentPage(liveHelper.id));
  const embed = await embedSection();

  expect(await within(embed).findByText("Today's usage could not be loaded.")).toBeInTheDocument();
  expect(within(embed).queryByRole("progressbar")).not.toBeInTheDocument();
});

test("an Editor sets the daily Token Budget and the meter follows", async () => {
  const user = userEvent.setup();
  const { requests } = setUp({ tokensUsed: 500 });
  renderStudio(agentPage(liveHelper.id));
  const embed = await embedSection();
  const field = within(embed).getByLabelText("Tokens per day");
  expect(await within(embed).findByDisplayValue("1000000")).toBe(field);

  await user.clear(field);
  await user.type(field, "2000");
  await user.click(within(embed).getByRole("button", { name: "Save Token Budget" }));

  expect(await within(embed).findByText("Saved. The new budget applies to the next message.")).toBeInTheDocument();
  expect(requests.filter((r) => r.route === "operational-settings")).toEqual([
    { route: "operational-settings", body: { daily_token_budget: 2000 } },
  ]);
  expect(await within(embed).findByText("500 of 2,000 tokens used today (25%).")).toBeInTheDocument();
  expect(field).toHaveValue(2000);
});

test("a refused Token Budget is explained", async () => {
  const user = userEvent.setup();
  setUp();
  server.use(
    http.patch(settingsPath, () =>
      HttpResponse.json(
        {
          detail: [
            {
              loc: ["body", "daily_token_budget"],
              msg: "Input should be less than or equal to 1000000000",
              type: "less_than_equal",
            },
          ],
        },
        { status: 422 },
      ),
    ),
  );
  renderStudio(agentPage(liveHelper.id));
  const embed = await embedSection();
  const field = await within(embed).findByDisplayValue("1000000");

  await user.clear(field);
  await user.type(field, "2000000000");
  await user.click(within(embed).getByRole("button", { name: "Save Token Budget" }));

  expect(await within(embed).findByRole("alert")).toHaveTextContent("Input should be less than or equal to 1000000000");
  await user.type(field, "5");
  expect(within(embed).queryByRole("alert")).not.toBeInTheDocument();
});

test("while the Operational Settings load, the Token Budget cannot be saved over", async () => {
  setUp();
  server.use(
    http.get(settingsPath, () => new Promise<Response>(() => undefined)),
    http.get(usagePath, () => new Promise<Response>(() => undefined)),
  );
  renderStudio(agentPage(liveHelper.id));
  const embed = await embedSection();

  expect(within(embed).getByLabelText("Tokens per day")).toBeDisabled();
  expect(within(embed).getByRole("button", { name: "Save Token Budget" })).toBeDisabled();
  expect(within(embed).queryByRole("progressbar")).not.toBeInTheDocument();
});
