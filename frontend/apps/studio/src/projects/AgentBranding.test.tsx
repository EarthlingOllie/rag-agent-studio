import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { fakeAgentsApi, hrHelper } from "../test/agents";
import { adaSession, fakeAuthApi, type Session } from "../test/auth";
import { anAvatar, fakeBrandingApi } from "../test/branding";
import { fakeProjectsApi, hrProject } from "../test/projects";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const agentPage = `/organisations/${organisationId}/projects/${hrProject.id}/agents/${hrHelper.id}/embed`;
const editorSession: Session = {
  ...adaSession,
  organisations: adaSession.organisations.map((organisation) => ({ ...organisation, role: "editor" as const })),
};
const OVERRIDE = "*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/theme-override";

function setUp(options: Parameters<typeof fakeBrandingApi>[0] = {}, session = adaSession) {
  fakeAuthApi({ signedInAs: session });
  fakeProjectsApi();
  fakeAgentsApi({ agents: [hrHelper] });
  return fakeBrandingApi(options);
}

async function branding() {
  const section = await screen.findByRole("region", { name: "Theme override" }, { timeout: 5000 });
  await within(section).findByRole("form", { name: "Colour override" });
  return section;
}

function png(name = "hana.png") {
  return new File(["png-bytes"], name, { type: "image/png" });
}

test("an Owner gives the Agent its own primary colour; the rest follow the Theme", async () => {
  const user = userEvent.setup();
  const requests = setUp();
  renderStudio(agentPage);
  const section = await branding();
  expect(within(section).getByText("Changes apply to the widget at once, without publishing.")).toBeInTheDocument();
  expect(within(section).queryByLabelText("Primary, light")).not.toBeInTheDocument();

  await user.click(within(section).getByRole("checkbox", { name: "Override primary" }));
  // It starts from the Theme's colour.
  const light = within(section).getByLabelText("Primary, light");
  expect(light).toHaveValue("#4f46e5");
  await user.clear(light);
  await user.type(light, "#AA0000");
  await user.click(within(section).getByRole("button", { name: "Save colours" }));

  expect(await within(section).findByText("Saved. The widget uses these colours now.")).toBeInTheDocument();
  expect(requests).toEqual([
    { route: "colours", body: { colours: { primary: { light: "#aa0000", dark: "#818cf8" } } } },
  ]);
  expect(within(section).getByLabelText("Primary, light")).toHaveValue("#aa0000");
});

test("a saved override shows ticked, and unticking it follows the Theme again", async () => {
  const user = userEvent.setup();
  const requests = setUp({ override: { colours: { accent: { light: "#123456", dark: "#abcdef" } }, avatar: null } });
  renderStudio(agentPage);
  const section = await branding();

  expect(within(section).getByRole("checkbox", { name: "Override accent" })).toBeChecked();
  expect(within(section).getByLabelText("Accent, dark")).toHaveValue("#abcdef");
  await user.click(within(section).getByRole("checkbox", { name: "Override accent" }));
  await user.click(within(section).getByRole("button", { name: "Save colours" }));

  expect(await within(section).findByText("Saved. The widget uses these colours now.")).toBeInTheDocument();
  expect(requests).toEqual([{ route: "colours", body: { colours: {} } }]);
});

test("a colour that isn't a hex colour can't be saved", async () => {
  const user = userEvent.setup();
  setUp();
  renderStudio(agentPage);
  const section = await branding();

  await user.click(within(section).getByRole("checkbox", { name: "Override surface" }));
  await user.clear(within(section).getByLabelText("Surface, dark"));
  await user.type(within(section).getByLabelText("Surface, dark"), "navy");

  expect(within(section).getByLabelText("Surface, dark")).toHaveAttribute("aria-invalid", "true");
  expect(within(section).getByText("Use colours like #1a2b3c.")).toBeInTheDocument();
  expect(within(section).getByRole("button", { name: "Save colours" })).toBeDisabled();
});

test("the API's reason for refusing the colours is shown", async () => {
  const user = userEvent.setup();
  setUp();
  server.use(
    http.put(OVERRIDE, () => HttpResponse.json({ detail: "Only Owners can do this" }, { status: 403 })),
  );
  renderStudio(agentPage);
  const section = await branding();

  await user.click(within(section).getByRole("checkbox", { name: "Override muted text" }));
  await user.click(within(section).getByRole("button", { name: "Save colours" }));

  expect(await within(section).findByText("Only Owners can do this")).toBeInTheDocument();
});

test.each([
  [{ detail: [{ msg: "String should match pattern" }] }, "String should match pattern"],
  [{ detail: [{}] }, "Something went wrong. Try again."],
  [{}, "Something went wrong. Try again."],
])("a refusal %j is explained", async (body, shown) => {
  const user = userEvent.setup();
  setUp();
  server.use(http.put(OVERRIDE, () => HttpResponse.json(body, { status: 422 })));
  renderStudio(agentPage);
  const section = await branding();

  await user.click(within(section).getByRole("button", { name: "Save colours" }));

  expect(await within(section).findByText(shown)).toBeInTheDocument();
});

test("an Owner uploads, replaces and removes the Agent's avatar", async () => {
  const requests = setUp();
  renderStudio(agentPage);
  const section = await branding();
  expect(within(section).getByText(/No avatar of its own/)).toBeInTheDocument();

  await userEvent.upload(within(section).getByLabelText("Upload avatar"), png());

  expect(await within(section).findByText("Avatar saved. The widget uses it now.")).toBeInTheDocument();
  expect(within(section).getByRole("img", { name: "The Agent's avatar" })).toHaveAttribute("src", anAvatar("1").url);
  await userEvent.upload(within(section).getByLabelText("Replace avatar"), png("newer.png"));
  await within(section).findByRole("img", { name: "The Agent's avatar" });
  expect(await within(section).findByRole("img", { name: "The Agent's avatar" })).toHaveAttribute("src", anAvatar("2").url);

  await userEvent.click(within(section).getByRole("button", { name: "Remove avatar" }));

  expect(await within(section).findByText("Avatar removed.")).toBeInTheDocument();
  expect(within(section).queryByRole("img", { name: "The Agent's avatar" })).not.toBeInTheDocument();
  expect(requests.map((request) => request.route)).toEqual(["start", "put", "confirm", "start", "put", "confirm", "remove"]);
  expect(requests[0]?.body).toEqual({ filename: "hana.png", size_bytes: 9 });
});

test("an avatar of the wrong type is refused with the API's reason", async () => {
  setUp();
  renderStudio(agentPage);
  const section = await branding();

  await userEvent.upload(within(section).getByLabelText("Upload avatar"), new File(["<svg/>"], "face.svg", { type: "image/svg+xml" }), {
    applyAccept: false,
  });

  expect(await within(section).findByRole("alert")).toHaveTextContent("Upload a PNG, JPEG or WebP image.");
});

test.each([
  ["storage refuses the file", () => { server.use(http.put("*/studio-documents/agent-avatar", () => new HttpResponse(null, { status: 403 }))); }],
  [
    "the confirmation is refused",
    () => { server.use(http.put(`${OVERRIDE}/avatar`, () => HttpResponse.json({ detail: "The file isn't a PNG image. Upload it again." }, { status: 422 }))); },
  ],
  ["the network fails", () => { server.use(http.post(`${OVERRIDE}/avatar/uploads`, () => HttpResponse.error())); }],
])("when %s, the upload fails with a reason", async (_, fail) => {
  setUp();
  fail();
  renderStudio(agentPage);
  const section = await branding();

  await userEvent.upload(within(section).getByLabelText("Upload avatar"), png());

  expect(await within(section).findByRole("alert")).toHaveTextContent(/Upload it again|The upload failed. Try again./);
});

test.each([
  ["refused", () => HttpResponse.json({ detail: "Only Owners can do this" }, { status: 403 })],
  ["a network failure", () => HttpResponse.error()],
])("removing the avatar can fail: %s", async (_, answer) => {
  setUp({ override: { colours: {}, avatar: anAvatar() } });
  server.use(http.delete(`${OVERRIDE}/avatar`, answer));
  renderStudio(agentPage);
  const section = await branding();

  await userEvent.click(within(section).getByRole("button", { name: "Remove avatar" }));

  expect(await within(section).findByRole("alert")).toHaveTextContent("The avatar couldn't be removed. Try again.");
});

test("Editors see the branding but can't change it", async () => {
  setUp({ override: { colours: { primary: { light: "#aa0000", dark: "#ff8888" } }, avatar: anAvatar() } }, editorSession);
  renderStudio(agentPage);
  const section = await branding();

  expect(within(section).getByText(/Only Owners can change the widget branding./)).toBeInTheDocument();
  expect(within(section).getByRole("checkbox", { name: "Override primary" })).toBeDisabled();
  expect(within(section).getByLabelText("Primary, light")).toBeDisabled();
  expect(within(section).queryByRole("button", { name: "Save colours" })).not.toBeInTheDocument();
  expect(within(section).getByRole("img", { name: "The Agent's avatar" })).toBeInTheDocument();
  expect(within(section).queryByLabelText("Replace avatar")).not.toBeInTheDocument();
  expect(within(section).queryByRole("button", { name: "Remove avatar" })).not.toBeInTheDocument();
});

test("when the branding can't be loaded, that is said", async () => {
  setUp();
  server.use(http.get(OVERRIDE, () => HttpResponse.json({ detail: "Not found" }, { status: 404 })));
  renderStudio(agentPage);

  const section = await screen.findByRole("region", { name: "Theme override" }, { timeout: 5000 });
  expect(await within(section).findByRole("alert")).toHaveTextContent("The widget branding could not be loaded.");
});
