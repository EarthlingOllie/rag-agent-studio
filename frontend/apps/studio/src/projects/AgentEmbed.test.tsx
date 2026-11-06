import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { fakeAgentsApi, hrHelper, oldHelper } from "../test/agents";
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
  expect(requests.filter((r) => r.route === "allowed-origins")).toEqual([
    { route: "allowed-origins", body: { origins: ["HTTPS://Shop.example.com/", "http://localhost:8080"] } },
  ]);
});

test("an invalid Allowed Origin is explained", async () => {
  const user = userEvent.setup();
  setUp();
  renderStudio(agentPage(liveHelper.id));
  const embed = await embedSection();
  const field = within(embed).getByLabelText("Allowed Origins");

  await user.type(field, "www.example.com");
  await user.click(within(embed).getByRole("button", { name: "Save Allowed Origins" }));

  expect(await within(embed).findByRole("alert")).toHaveTextContent(
    "'www.example.com' isn't a site address. Use a scheme, host and optional port, such as https://www.example.com or http://localhost:8080.",
  );
  expect(field).toHaveValue("www.example.com");
});

test("other failures to save or load the Allowed Origins are reported", async () => {
  const user = userEvent.setup();
  setUp();
  const path = "*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/allowed-origins";
  server.use(
    http.get(path, () => HttpResponse.json({ detail: "Not Found" }, { status: 404 })),
    http.put(path, () => HttpResponse.json({ detail: "Boom" }, { status: 500 })),
  );
  renderStudio(agentPage(liveHelper.id));
  const embed = await embedSection();

  expect(await within(embed).findByText("The Allowed Origins could not be loaded.")).toBeInTheDocument();
  await user.click(within(embed).getByRole("button", { name: "Save Allowed Origins" }));
  expect(await within(embed).findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});
