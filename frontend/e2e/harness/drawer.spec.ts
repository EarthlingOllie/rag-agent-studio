import { navigationButton, openDrawer } from "../fixtures/navigation";
import { expect, test } from "./test";

/**
 * A stand-in for the Studio's frame on a phone: the top bar's "Open navigation" button, and the
 * sidebar hidden until the button turns it into a dialog named "Navigation".
 */
const FRAME = `<!doctype html><html lang="en"><title>Drawer</title>
<header>
  <button type="button" aria-label="Open navigation" aria-expanded="false" id="open">=</button>
</header>
<aside id="drawer" hidden>
  <nav aria-label="Studio">
    <ul aria-label="Organisation sections"><li><a href="#Projects" aria-current="page">Projects</a></li></ul>
  </nav>
</aside>
<main><h1>Projects</h1></main>
<script>
  document.getElementById("open").addEventListener("click", () => {
    // The drawer arrives a moment later, as a rendered one would.
    setTimeout(() => {
      const drawer = document.getElementById("drawer");
      drawer.hidden = false;
      drawer.setAttribute("role", "dialog");
      drawer.setAttribute("aria-label", "Navigation");
    }, 100);
  });
</script></html>`;

test.describe("drawer helpers", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.setContent(FRAME);
  });

  test("navigationButton is the top bar's Open navigation button", async ({ page }) => {
    await expect(navigationButton(page)).toHaveAttribute("id", "open");
  });

  test("openDrawer presses it and returns the drawer once its navigation is shown", async ({ page }) => {
    const drawer = await openDrawer(page);

    await expect(drawer.getByRole("link", { name: "Projects" })).toHaveAttribute("aria-current", "page");
  });
});
