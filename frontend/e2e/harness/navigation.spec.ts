import { currentSection, menuButton, openSection, sectionNames } from "../fixtures/navigation";
import { expect, test } from "./test";

/**
 * A stand-in for the Studio's frame: a top bar with a breadcrumb switcher and an account menu, and
 * a sidebar (the navigation landmark "Studio") with an Organisation switcher and a group of
 * Organisation section links. A menu opens on click and closes on Escape, its items carrying number
 * hints hidden from assistive technology. Following a link writes it into the page's heading, so a
 * spec can see which one was followed; the followed sidebar link becomes the current one.
 */
const FRAME = `<!doctype html><html lang="en"><title>Navigation</title>
<header>
  <nav aria-label="Breadcrumb"><button type="button" aria-label="Projects, Organisation sections" aria-haspopup="menu" data-menu="crumb">Projects</button></nav>
  <div role="menu" id="crumb" aria-label="Organisation sections" hidden>
    <a role="menuitem" href="#Security">Security <span aria-hidden="true">4</span></a>
  </div>
  <button type="button" aria-haspopup="menu" data-menu="account"><span class="sr">Ada Lovelace, Account</span></button>
  <div role="menu" id="account" aria-label="Account" hidden>
    <a role="menuitem" href="#Profile">Profile</a>
    <a role="menuitem" href="#Security">Security</a>
  </div>
</header>
<aside>
  <nav aria-label="Studio">
    <button type="button" aria-label="Analytical Engines, Organisations" aria-haspopup="menu" data-menu="organisations">Analytical Engines</button>
    <div role="menu" id="organisations" aria-label="Organisations" hidden>
      <a role="menuitem" href="#Analytical Engines">Analytical Engines</a>
      <a role="menuitem" href="#Difference Engines">Difference Engines</a>
    </div>
    <ul aria-label="Organisation sections">
      <li><a href="#Projects" aria-current="page"><svg aria-hidden="true"></svg>Projects</a></li>
      <li><a href="#Cost"><svg aria-hidden="true"></svg>Cost</a></li>
      <li><a href="#Settings"><svg aria-hidden="true"></svg>Settings</a></li>
    </ul>
  </nav>
</aside>
<main>
  <h1>Projects</h1>
</main>
<script>
  const menus = document.querySelectorAll("[role=menu]");
  document.querySelectorAll("[data-menu]").forEach((button) => {
    button.addEventListener("click", () => { document.getElementById(button.dataset.menu).hidden = false; });
  });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") menus.forEach((menu) => { menu.hidden = true; }); });
  window.addEventListener("hashchange", () => {
    menus.forEach((menu) => { menu.hidden = true; });
    const here = decodeURIComponent(location.hash.slice(1));
    document.querySelector("h1").textContent = here;
    document.querySelectorAll("[aria-label='Organisation sections'] a").forEach((link) => {
      if (link.textContent === here) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
  });
</script></html>`;

test.describe("navigation helpers", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.setContent(FRAME);
  });

  test("openSection follows a sidebar link, not the breadcrumb switcher's item of the same name", async ({ page }) => {
    await openSection(page, "Organisation sections", "Settings");

    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Settings");
    expect(await currentSection(page, "Organisation sections")).toBe("Settings");
  });

  test("sectionNames lists a sidebar group's links, without their hidden icons", async ({ page }) => {
    expect(await sectionNames(page, "Organisation sections")).toEqual(["Projects", "Cost", "Settings"]);
    expect(await currentSection(page, "Organisation sections")).toBe("Projects");
  });

  test("the Organisations switcher is the sidebar's", async ({ page }) => {
    await expect(menuButton(page, "Organisations")).toHaveAccessibleName("Analytical Engines, Organisations");
    expect(await sectionNames(page, "Organisations")).toEqual(["Analytical Engines", "Difference Engines"]);
    await expect(page.getByRole("menu", { name: "Organisations" })).toBeHidden();

    await openSection(page, "Organisations", "Difference Engines");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Difference Engines");
  });

  test("a top bar menu opens, is listed and closes as before", async ({ page }) => {
    expect(await sectionNames(page, "Account")).toEqual(["Profile", "Security"]);
    await expect(page.getByRole("menu", { name: "Account" })).toBeHidden();
    await expect(menuButton(page, "Account")).toBeVisible();

    await openSection(page, "Account", "Security");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Security");
  });
});
