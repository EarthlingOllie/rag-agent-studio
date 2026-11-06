import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi } from "../test/auth";
import { renderStudio } from "../test/render";
import { server } from "../test/server";
import { anImage, defaultTheme, fakeThemeApi, UNSUPPORTED_IMAGE } from "../test/theme";

const organisationId = adaSession.organisations[0]?.id ?? "";
const themePath = `/organisations/${organisationId}/settings/theme`;
const editorSession = {
  ...adaSession,
  organisations: adaSession.organisations.map((organisation) => ({ ...organisation, role: "editor" as const })),
};

function preview() {
  return screen.getByRole("group", { name: "Widget preview (light)" });
}

function images() {
  return screen.getByRole("region", { name: "Logo and avatar" });
}

function png(name = "brand.png") {
  return new File(["png-bytes"], name, { type: "image/png" });
}

async function openImages() {
  await screen.findByRole("form", { name: "Theme" });
  return images();
}

test("an Owner uploads a logo through a presigned upload and the preview shows it at once", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  const api = fakeThemeApi();
  renderStudio(themePath);
  const section = await openImages();
  expect(within(section).getByText("No logo yet.")).toBeInTheDocument();
  expect(within(preview()).queryByRole("img", { name: "Logo" })).not.toBeInTheDocument();

  await userEvent.upload(within(section).getByLabelText("Upload logo"), png());

  await within(section).findByText("Logo saved. The widget uses it now.");
  expect(within(section).getByRole("status", { name: "Logo" })).toHaveTextContent("Logo saved. The widget uses it now.");
  // Presign (the API checks type and size), PUT straight to storage, then confirm.
  expect(api.requests).toEqual([
    { route: "start", kind: "logo", body: { filename: "brand.png", size_bytes: 9 } },
    { route: "put", kind: "theme-logo", body: "png-bytes", contentType: "image/png" },
    { route: "confirm", kind: "logo", body: { upload_id: "upload-logo" } },
  ]);
  expect(within(preview()).getByRole("img", { name: "Logo" })).toHaveAttribute("src", anImage("logo").url);
  expect(within(section).getByRole("img", { name: "Current logo" })).toHaveAttribute("src", anImage("logo").url);
  expect(within(section).getByText("PNG, 2.0 KB")).toBeInTheDocument();
});

test("an Owner uploads the default Agent avatar and the preview's chat header shows it", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeThemeApi();
  renderStudio(themePath);
  const section = await openImages();
  expect(within(section).getByText("No avatar yet.")).toBeInTheDocument();

  await userEvent.upload(within(section).getByLabelText("Upload avatar"), png("face.png"));

  expect(await within(preview()).findByRole("img", { name: "Assistant's avatar" })).toHaveAttribute("src", anImage("avatar", "1").url);
  expect(within(section).getByRole("status", { name: "Avatar" })).toHaveTextContent("Avatar saved. The widget uses it now.");
});

test("saved images show in the preview and can be replaced and removed", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  const api = fakeThemeApi({ theme: { ...defaultTheme, logo: anImage("logo", "old"), avatar: anImage("avatar", "old") } });
  renderStudio(themePath);
  const section = await openImages();
  expect(within(preview()).getByRole("img", { name: "Logo" })).toHaveAttribute("src", anImage("logo", "old").url);

  await userEvent.upload(within(section).getByLabelText("Replace logo"), png("new.png"));
  await within(section).findByText("Logo saved. The widget uses it now.");
  expect(within(preview()).getByRole("img", { name: "Logo" })).toHaveAttribute("src", anImage("logo", "1").url);

  await userEvent.click(within(section).getByRole("button", { name: "Remove avatar" }));

  expect(await within(section).findByText("Avatar removed.")).toBeInTheDocument();
  expect(within(section).getByText("No avatar yet.")).toBeInTheDocument();
  expect(within(preview()).queryByRole("img", { name: "Assistant's avatar" })).not.toBeInTheDocument();
  expect(within(preview()).getByRole("img", { name: "Logo" })).toBeInTheDocument();
  expect(api.requests.at(-1)).toEqual({ route: "remove", kind: "avatar" });
});

test("images apply on their own: they don't wait for Save Theme or change the draft", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  const api = fakeThemeApi();
  renderStudio(themePath);
  const section = await openImages();
  const primary = screen.getByLabelText("Primary (light)");
  await userEvent.clear(primary);
  await userEvent.type(primary, "#b91c1c");

  await userEvent.upload(within(section).getByLabelText("Upload logo"), png());
  await within(section).findByText("Logo saved. The widget uses it now.");

  // The unsaved colour edit is still in the editor and the preview.
  expect(screen.getByLabelText("Primary (light)")).toHaveValue("#b91c1c");
  expect(preview().style.getPropertyValue("--theme-primary")).toBe("#b91c1c");
  expect(api.saved).toEqual([]);
});

test("a file type the API refuses shows its reason and changes nothing", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  const api = fakeThemeApi();
  renderStudio(themePath);
  const section = await openImages();

  await userEvent.upload(within(section).getByLabelText("Upload logo"), new File(["<svg/>"], "logo.svg", { type: "image/svg+xml" }), {
    applyAccept: false,
  });

  expect(await within(section).findByRole("alert")).toHaveTextContent(UNSUPPORTED_IMAGE);
  expect(api.requests.map((request) => request.route)).toEqual(["start"]);
  expect(within(section).getByText("No logo yet.")).toBeInTheDocument();
});

test("a stored file the API refuses on confirm shows its reason", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeThemeApi();
  server.use(
    http.put("*/api/organisations/:organisationId/theme/images/:kind", () =>
      HttpResponse.json({ detail: "The file isn't a PNG image. Upload it again." }, { status: 422 }),
    ),
  );
  renderStudio(themePath);
  const section = await openImages();

  await userEvent.upload(within(section).getByLabelText("Upload avatar"), png());

  expect(await within(section).findByRole("alert")).toHaveTextContent("The file isn't a PNG image. Upload it again.");
});

test("a failed PUT to storage, or an answer without a reason, says to try again", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeThemeApi();
  server.use(http.put("*/studio-documents/:key", () => new HttpResponse(null, { status: 403 })));
  renderStudio(themePath);
  const section = await openImages();

  await userEvent.upload(within(section).getByLabelText("Upload logo"), png());
  expect(await within(section).findByRole("alert")).toHaveTextContent("The upload failed. Try again.");

  server.use(http.post("*/api/organisations/:organisationId/theme/images/:kind/uploads", () => HttpResponse.json({}, { status: 500 })));
  await userEvent.upload(within(section).getByLabelText("Upload avatar"), png());
  await vi.waitFor(() => {
    expect(within(section).getAllByRole("alert").map((alert) => alert.textContent)).toEqual([
      "The upload failed. Try again.",
      "The upload failed. Try again.",
    ]);
  });
});

test("a PUT to storage or a removal that can't reach the server says to try again and frees the controls", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeThemeApi({ theme: { ...defaultTheme, avatar: anImage("avatar") } });
  server.use(
    http.put("*/studio-documents/:key", () => HttpResponse.error()),
    http.delete("*/api/organisations/:organisationId/theme/images/:kind", () => HttpResponse.error()),
  );
  renderStudio(themePath);
  const section = await openImages();

  await userEvent.upload(within(section).getByLabelText("Upload logo"), png());
  expect(await within(section).findByRole("alert")).toHaveTextContent("The upload failed. Try again.");
  expect(within(section).getByLabelText("Upload logo")).toBeEnabled();

  await userEvent.click(within(section).getByRole("button", { name: "Remove avatar" }));
  await vi.waitFor(() => {
    expect(within(section).getAllByRole("alert").map((alert) => alert.textContent)).toEqual([
      "The upload failed. Try again.",
      "The image couldn't be removed. Try again.",
    ]);
  });
  expect(within(section).getByRole("button", { name: "Remove avatar" })).toBeEnabled();
  expect(within(section).getByRole("img", { name: "Current avatar" })).toBeInTheDocument();
});

test("a confirmation that can't reach the API says to try again", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeThemeApi();
  server.use(http.put("*/api/organisations/:organisationId/theme/images/:kind", () => HttpResponse.error()));
  renderStudio(themePath);
  const section = await openImages();

  await userEvent.upload(within(section).getByLabelText("Upload logo"), png());

  expect(await within(section).findByRole("alert")).toHaveTextContent("The upload failed. Try again.");
  expect(within(section).getByLabelText("Upload logo")).toBeEnabled();
  expect(within(section).getByText("No logo yet.")).toBeInTheDocument();
});

test("the controls say so while an image is uploading or being removed, and a failed removal says to try again", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeThemeApi({ theme: { ...defaultTheme, logo: anImage("logo") } });
  server.use(
    http.delete("*/api/organisations/:organisationId/theme/images/:kind", async () => {
      await delay(50);
      return HttpResponse.json({ detail: "Boom" }, { status: 500 });
    }),
  );
  renderStudio(themePath);
  const section = await openImages();

  await userEvent.click(within(section).getByRole("button", { name: "Remove logo" }));

  expect(within(section).getByRole("button", { name: "Removing…" })).toBeDisabled();
  expect(within(section).getByLabelText("Replace logo")).toBeDisabled();
  expect(await within(section).findByRole("alert")).toHaveTextContent("The image couldn't be removed. Try again.");
  expect(within(section).getByRole("img", { name: "Current logo" })).toBeInTheDocument();
});

test("the upload shows its progress while it runs", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeThemeApi();
  server.use(
    http.put("*/studio-documents/:key", async () => {
      await delay(50);
      return new HttpResponse(null, { status: 200 });
    }),
  );
  renderStudio(themePath);
  const section = await openImages();

  await userEvent.upload(within(section).getByLabelText("Upload logo"), png());

  expect(within(section).getByText("Uploading…")).toBeInTheDocument();
  expect(within(section).getByLabelText("Upload logo")).toBeDisabled();
  expect(await within(section).findByText("Logo saved. The widget uses it now.")).toBeInTheDocument();
});

test("Editors see the images in the editor and the preview but can't upload or remove them", async () => {
  fakeAuthApi({ signedInAs: editorSession });
  const api = fakeThemeApi({ theme: { ...defaultTheme, logo: anImage("logo") } });
  renderStudio(themePath);
  const section = await openImages();

  expect(within(section).getByRole("img", { name: "Current logo" })).toBeInTheDocument();
  expect(within(preview()).getByRole("img", { name: "Logo" })).toBeInTheDocument();
  expect(within(section).getByLabelText("Replace logo")).toBeDisabled();
  expect(within(section).getByLabelText("Upload avatar")).toBeDisabled();
  expect(within(section).queryByRole("button", { name: "Remove logo" })).not.toBeInTheDocument();
  expect(api.requests).toEqual([]);
});
