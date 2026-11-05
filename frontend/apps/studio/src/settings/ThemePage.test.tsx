import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi } from "../test/auth";
import { renderStudio } from "../test/render";
import { server } from "../test/server";
import { defaultTheme, fakeThemeApi } from "../test/theme";

const organisationId = adaSession.organisations[0]?.id ?? "";
const themePath = `/organisations/${organisationId}/settings/theme`;
const editorSession = {
  ...adaSession,
  organisations: adaSession.organisations.map((organisation) => ({ ...organisation, role: "editor" as const })),
};

function preview(scheme = "light") {
  return screen.getByRole("group", { name: `Widget preview (${scheme})` });
}

function property(element: HTMLElement, name: string) {
  return element.style.getPropertyValue(name);
}

async function openEditor() {
  return screen.findByRole("form", { name: "Theme" });
}

async function setText(label: string, value: string) {
  const input = screen.getByLabelText(label);
  await userEvent.clear(input);
  await userEvent.type(input, value);
}

test("every Member finds the Theme tab in Organisation settings", async () => {
  fakeAuthApi({ signedInAs: editorSession });
  fakeThemeApi();
  renderStudio(`/organisations/${organisationId}/settings`);

  const tabs = await screen.findByRole("navigation", { name: "Organisation settings" });
  await userEvent.click(within(tabs).getByRole("link", { name: "Theme" }));

  expect(await screen.findByRole("heading", { name: "Theme" })).toBeInTheDocument();
});

test("the preview renders the widget's primitives with the saved Theme", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeThemeApi();
  renderStudio(themePath);
  await openEditor();

  const widget = preview();
  expect(property(widget, "--theme-primary")).toBe("#4f46e5");
  expect(property(widget, "--theme-radius")).toBe("12px");
  expect(property(widget, "--theme-font-family")).toBe('"Inter", ui-sans-serif, system-ui, sans-serif');
  expect(within(widget).getByRole("region", { name: "Chat with Assistant" })).toBeInTheDocument();
  expect(within(widget).getByText("Hi! How can I help you today?")).toBeInTheDocument();
  expect(within(widget).getByRole("textbox", { name: "Message" })).toBeInTheDocument();
  expect(within(widget).getByRole("button", { name: "Close chat" })).toHaveAttribute("data-position", "bottom-right");
  // The font comes from Google Fonts, by its allowlisted family.
  expect(document.querySelector('link[rel="stylesheet"]')).toHaveAttribute(
    "href",
    "https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap",
  );
});

test("the bubble launcher opens and closes the chat in the preview", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeThemeApi();
  renderStudio(themePath);
  await openEditor();

  await userEvent.click(within(preview()).getByRole("button", { name: "Close chat" }));

  expect(within(preview()).queryByRole("region", { name: "Chat with Assistant" })).not.toBeInTheDocument();
  await userEvent.click(within(preview()).getByRole("button", { name: "Open chat" }));
  expect(within(preview()).getByRole("region", { name: "Chat with Assistant" })).toBeInTheDocument();
});

test("the preview's message box is for show: sending does nothing", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeThemeApi();
  renderStudio(themePath);
  await openEditor();
  const widget = preview();

  await userEvent.type(within(widget).getByRole("textbox", { name: "Message" }), "Hello");
  await userEvent.click(within(widget).getByRole("button", { name: "Send" }));

  expect(screen.getByRole("heading", { name: "Theme" })).toBeInTheDocument();
});

test("the preview updates live as the Owner edits, before saving", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  const api = fakeThemeApi();
  renderStudio(themePath);
  await openEditor();

  await setText("Primary (light)", "#b91c1c");
  await setText("Corner radius (px)", "4");
  await userEvent.selectOptions(screen.getByLabelText("Font"), "Merriweather");

  const widget = preview();
  expect(property(widget, "--theme-primary")).toBe("#b91c1c");
  expect(property(widget, "--theme-radius")).toBe("4px");
  expect(property(widget, "--theme-font-family")).toBe('"Merriweather", ui-sans-serif, system-ui, sans-serif');
  expect(api.saved).toEqual([]);
});

test("the colour picker and the hex field edit the same token", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeThemeApi();
  renderStudio(themePath);
  await openEditor();

  fireEvent.input(screen.getByLabelText("Accent (dark) colour picker"), { target: { value: "#22c55e" } });

  expect(screen.getByLabelText("Accent (dark)")).toHaveValue("#22c55e");
});

test("an unfinished hex colour is flagged and keeps the preview on the last valid one", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeThemeApi();
  renderStudio(themePath);
  await openEditor();

  await setText("Surface (light)", "#fff");

  expect(screen.getByText("Use a colour like #1a2b3c.")).toBeInTheDocument();
  expect(screen.getByLabelText("Surface (light)")).toHaveAttribute("aria-invalid", "true");
  expect(property(preview(), "--theme-surface")).toBe("#ffffff");
  expect(screen.getByRole("button", { name: "Save Theme" })).toBeDisabled();

  await setText("Surface (light)", "#FAFAF9");
  expect(property(preview(), "--theme-surface")).toBe("#fafaf9");
  expect(screen.queryByText("Use a colour like #1a2b3c.")).not.toBeInTheDocument();
});

test("a corner radius outside 0 to 24 is flagged and can't be saved", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeThemeApi();
  renderStudio(themePath);
  await openEditor();

  await setText("Corner radius (px)", "40");

  expect(screen.getByText("Use a whole number from 0 to 24.")).toBeInTheDocument();
  // Typing "40" passed through "4", the last valid radius, which the preview keeps.
  expect(property(preview(), "--theme-radius")).toBe("4px");
  expect(screen.getByRole("button", { name: "Save Theme" })).toBeDisabled();
});

test("the inline launcher shows the chat in a container, with no bubble or position", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeThemeApi();
  renderStudio(themePath);
  await openEditor();

  await userEvent.click(screen.getByRole("radio", { name: "Bottom left" }));
  expect(within(preview()).getByRole("button", { name: "Close chat" })).toHaveAttribute("data-position", "bottom-left");
  await userEvent.click(screen.getByRole("radio", { name: "Inline container" }));

  expect(within(preview()).queryByRole("button", { name: /chat/ })).not.toBeInTheDocument();
  expect(within(preview()).getByRole("region", { name: "Chat with Assistant" })).toBeInTheDocument();
  expect(screen.queryByRole("radiogroup", { name: "Bubble position" })).not.toBeInTheDocument();
});

test("dark mode previews the dark values; automatic previews either", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeThemeApi();
  renderStudio(themePath);
  await openEditor();

  await userEvent.click(screen.getByRole("radio", { name: "Dark" }));
  expect(property(preview("dark"), "--theme-primary")).toBe("#818cf8");
  expect(screen.queryByRole("radiogroup", { name: "Preview colours" })).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole("radio", { name: "Automatic" }));
  const previewColours = screen.getByRole("radiogroup", { name: "Preview colours" });
  expect(preview("light")).toBeInTheDocument();
  await userEvent.click(within(previewColours).getByRole("radio", { name: "Dark" }));
  expect(property(preview("dark"), "--theme-surface")).toBe("#111827");
  await userEvent.click(within(previewColours).getByRole("radio", { name: "Light" }));
  expect(property(preview("light"), "--theme-surface")).toBe("#ffffff");
});

test("a pair that fails WCAG AA shows a warning that goes away once fixed, and never blocks saving", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  const api = fakeThemeApi();
  renderStudio(themePath);
  await openEditor();
  const contrast = screen.getByRole("status", { name: "Contrast" });
  expect(within(contrast).queryByRole("listitem")).not.toBeInTheDocument();

  await setText("Text on surface (light)", "#d1d5db");

  expect(within(contrast).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
    "Text on surface (#d1d5db on #ffffff) has a contrast of 1.47:1 in light mode. WCAG AA needs 4.5:1.",
  ]);
  expect(within(contrast).getByText(/You can still save/)).toBeInTheDocument();
  const save = screen.getByRole("button", { name: "Save Theme" });
  expect(save).toBeEnabled();

  await setText("Text on surface (light)", "#374151");
  expect(within(contrast).queryByRole("listitem")).not.toBeInTheDocument();

  await setText("Text on surface (light)", "#d1d5db");
  await userEvent.click(save);
  expect(await screen.findByText("Theme saved. The widget uses it now.")).toBeInTheDocument();
  expect(api.saved.map((theme) => theme.colours.on_surface.light)).toEqual(["#d1d5db"]);
});

test("dark-mode values are only checked when the Theme shows them", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeThemeApi();
  renderStudio(themePath);
  await openEditor();
  const contrast = screen.getByRole("status", { name: "Contrast" });

  await setText("Muted text (dark)", "#1f2937");
  expect(within(contrast).queryByRole("listitem")).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole("radio", { name: "Automatic" }));
  expect(within(contrast).getByRole("listitem")).toHaveTextContent("in dark mode");
});

test("Owners save the whole Theme and are told it applies at once", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  const api = fakeThemeApi();
  renderStudio(themePath);
  await openEditor();

  await setText("Primary (light)", "#B91C1C");
  await setText("Primary (dark)", "#f87171");
  await setText("Corner radius (px)", "0");
  await userEvent.selectOptions(screen.getByLabelText("Font"), "Roboto");
  await userEvent.click(screen.getByRole("radio", { name: "Automatic" }));
  await userEvent.click(screen.getByRole("radio", { name: "Bottom left" }));
  await userEvent.click(screen.getByRole("button", { name: "Save Theme" }));

  expect(await screen.findByRole("status", { name: "Saved" })).toHaveTextContent("Theme saved. The widget uses it now.");
  expect(api.saved).toEqual([
    {
      ...Object.fromEntries(Object.entries(defaultTheme).filter(([key]) => key !== "updated_at")),
      colours: { ...defaultTheme.colours, primary: { light: "#b91c1c", dark: "#f87171" } },
      radius: 0,
      font: "Roboto",
      mode: "auto",
      launcher_position: "bottom-left",
    },
  ]);
});

test("editing after a save clears the saved message", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeThemeApi();
  renderStudio(themePath);
  await openEditor();
  await userEvent.click(screen.getByRole("button", { name: "Save Theme" }));
  expect(await screen.findByText("Theme saved. The widget uses it now.")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("radio", { name: "Dark" }));

  expect(screen.queryByText("Theme saved. The widget uses it now.")).not.toBeInTheDocument();
});

test("the Save button says so while saving, and a failed save says to try again", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeThemeApi();
  server.use(
    http.put("*/api/organisations/:organisationId/theme", async () => {
      await delay(50);
      return HttpResponse.json({ detail: "Boom" }, { status: 500 });
    }),
  );
  renderStudio(themePath);
  await openEditor();

  await userEvent.click(screen.getByRole("button", { name: "Save Theme" }));

  expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});

test("Editors see the Theme and its preview but can't change it", async () => {
  fakeAuthApi({ signedInAs: editorSession });
  const api = fakeThemeApi({ theme: { ...defaultTheme, radius: 6, launcher_type: "inline" } });
  renderStudio(themePath);
  const form = await openEditor();

  expect(screen.getByText("Only Owners can change the Theme.")).toBeInTheDocument();
  expect(within(form).getByLabelText("Primary (light)")).toBeDisabled();
  expect(within(form).getByLabelText("Font")).toBeDisabled();
  expect(within(form).getByRole("radio", { name: "Inline container" })).toBeChecked();
  expect(within(form).queryByRole("button", { name: "Save Theme" })).not.toBeInTheDocument();
  expect(property(preview(), "--theme-radius")).toBe("6px");
  expect(api.saved).toEqual([]);
});

test("the Theme page shows its loading and error states", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeThemeApi();
  server.use(
    http.get("*/api/organisations/:organisationId/theme", async () => {
      await delay(50);
      return HttpResponse.json({ detail: "Boom" }, { status: 500 });
    }),
  );
  renderStudio(themePath);

  expect(await screen.findByText("Loading the Theme…")).toBeInTheDocument();
  expect(await screen.findByRole("alert")).toHaveTextContent("The Theme could not be loaded. Try again.");
});

test("a failed font list also stops the editor loading", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeThemeApi();
  server.use(http.get("*/api/themes/fonts", () => HttpResponse.json({ detail: "Boom" }, { status: 500 })));
  renderStudio(themePath);

  expect(await screen.findByRole("alert")).toHaveTextContent("The Theme could not be loaded. Try again.");
});
