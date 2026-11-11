import { screen } from "@testing-library/react";

import { APPEARANCE_KEY } from "./design";

beforeEach(() => {
  vi.resetModules();
});

afterEach(() => {
  window.localStorage.clear();
  delete document.documentElement.dataset.appearance;
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

test.each(["light", "dark"] as const)(
  "opens in the %s Appearance the Member chose, before anything is drawn",
  async (appearance) => {
    window.localStorage.setItem(APPEARANCE_KEY, appearance);
    document.body.innerHTML = '<div id="root"></div>';
    const root = document.getElementById("root") as HTMLElement;
    // What <html> says at the moment the Studio first puts anything on the page.
    let atFirstPaint: string | undefined = "nothing drawn";
    const observer = new MutationObserver(() => {
      if (atFirstPaint === "nothing drawn") atFirstPaint = document.documentElement.dataset.appearance;
    });
    observer.observe(root, { childList: true, subtree: true });

    await import("./main");
    await screen.findByRole("heading", { name: "Sign in" });
    observer.disconnect();

    expect(atFirstPaint).toBe(appearance);
  },
);

test("follows the system until the Member chooses", async () => {
  document.body.innerHTML = '<div id="root"></div>';

  await import("./main");
  await screen.findByRole("heading", { name: "Sign in" });

  expect(document.documentElement).not.toHaveAttribute("data-appearance");
});
