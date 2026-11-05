import { screen } from "@testing-library/react";

beforeEach(() => {
  vi.resetModules();
});

test("mounts the Studio into the page's root element", async () => {
  document.body.innerHTML = '<div id="root"></div>';

  await import("./main");

  // A visitor who is not signed in lands on the sign-in screen.
  expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
});

test("explains what is missing when the page has no root element", async () => {
  document.body.innerHTML = "";

  await expect(import("./main")).rejects.toThrow("The Studio needs a #root element to mount into.");
});
