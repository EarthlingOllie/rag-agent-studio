import { screen } from "@testing-library/react";

beforeEach(() => {
  vi.resetModules();
  document.head.innerHTML = "";
});

test("mounts the widget with what the shell hands it", async () => {
  document.body.innerHTML =
    '<div id="root"></div><script id="widget-boot" type="application/json">{"agent":"agt_hr","name":"HR helper","bootstrap_token":"t"}</script>';

  await import("./main");

  expect(await screen.findByRole("heading", { name: "HR helper" })).toBeInTheDocument();
  expect(document.head.querySelector("style")?.textContent).toContain(".widget");
});

test("explains what is missing when the shell has no boot data", async () => {
  document.body.innerHTML = '<div id="root"></div>';

  await expect(import("./main")).rejects.toThrow("The widget needs the shell's #root and #widget-boot elements.");
});
