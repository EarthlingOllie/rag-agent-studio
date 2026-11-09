import { menuButton, openSection, sectionNames } from "../fixtures/navigation";
import { expect, test } from "./test";

/**
 * A stand-in for the Studio's top bar: a breadcrumb switcher whose menu opens on click and closes
 * on Escape, its items carrying number hints hidden from assistive technology, and a tab row a later slice has not yet replaced. Following an item writes it into
 * the page's heading, so a spec can see which one was followed.
 */
const TOP_BAR = `<!doctype html><html lang="en"><title>Navigation</title>
<header>
  <nav aria-label="Breadcrumb"><button type="button" id="sections" aria-label="Projects, Organisation sections" aria-haspopup="menu">Projects</button></nav>
  <div role="menu" aria-label="Organisation sections" hidden>
    <a role="menuitem" href="#Projects">Projects <span aria-hidden="true">1</span></a>
    <a role="menuitem" href="#Cost">Cost <span aria-hidden="true">2</span></a>
    <a role="menuitem" href="#Settings">Settings <span aria-hidden="true">3</span></a>
  </div>
</header>
<main>
  <h1>Projects</h1>
  <nav aria-label="Organisation settings"><a href="#General">General</a> <a href="#Members">Members</a></nav>
</main>
<script>
  const menu = document.querySelector("[role=menu]");
  document.getElementById("sections").addEventListener("click", () => { menu.hidden = false; });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") menu.hidden = true; });
  window.addEventListener("hashchange", () => {
    menu.hidden = true;
    document.querySelector("h1").textContent = decodeURIComponent(location.hash.slice(1));
  });
</script></html>`;

test.describe("navigation helpers", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.setContent(TOP_BAR);
  });

  test("openSection opens a switcher and follows its item", async ({ page }) => {
    await openSection(page, "Organisation sections", "Settings");

    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Settings");
  });

  test("openSection follows a tab in a row not yet replaced by a switcher", async ({ page }) => {
    await openSection(page, "Organisation settings", "Members");

    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Members");
  });

  test("sectionNames lists a switcher's items, without their hidden number hints, and closes it", async ({ page }) => {
    expect(await sectionNames(page, "Organisation sections")).toEqual(["Projects", "Cost", "Settings"]);
    await expect(page.getByRole("menu", { name: "Organisation sections" })).toBeHidden();
    await expect(menuButton(page, "Organisation sections")).toBeVisible();
  });

  test("sectionNames lists a tab row's tabs", async ({ page }) => {
    expect(await sectionNames(page, "Organisation settings")).toEqual(["General", "Members"]);
  });
});
