import { currentSection, menuButton, openSection, sectionNames } from "../fixtures/navigation";
import { expect, test } from "./test";

/**
 * A stand-in for an Agent page: the breadcrumb still holds an Agent switcher and a view switcher
 * (until the breadcrumb becomes plain links), and the main content holds the Agent's header with
 * its ▾ switcher and the tab row "Agent views". Following a link writes it into the page's heading
 * and marks the followed tab current, so a spec can see which one was followed.
 */
const FRAME = `<!doctype html><html lang="en"><title>Agent</title>
<header>
  <nav aria-label="Breadcrumb">
    <button type="button" aria-label="HR helper, Agents" aria-haspopup="menu" data-menu="crumb-agents">HR helper</button>
    <div role="menu" id="crumb-agents" aria-label="Agents" hidden>
      <a role="menuitem" href="#Crumb HR helper">HR helper</a>
    </div>
    <button type="button" aria-label="Playground, Agent views" aria-haspopup="menu" data-menu="crumb-views">Playground</button>
    <div role="menu" id="crumb-views" aria-label="Agent views" hidden>
      <a role="menuitem" href="#Crumb Versions">Versions</a>
    </div>
  </nav>
</header>
<main>
  <section aria-labelledby="agent">
    <h1 id="agent">HR helper</h1>
    <button type="button" aria-label="HR helper, Agents" aria-haspopup="menu" data-menu="agents"><svg aria-hidden="true"></svg></button>
    <div role="menu" id="agents" aria-label="Agents" hidden>
      <a role="menuitem" href="#HR helper">HR helper</a>
      <a role="menuitem" href="#Pay helper">Pay helper</a>
    </div>
  </section>
  <nav aria-label="Agent views">
    <ul>
      <li><a href="#Playground" aria-current="page">Playground</a></li>
      <li><a href="#Versions">Versions</a></li>
      <li><a href="#Embed &amp; limits">Embed &amp; limits</a></li>
      <li><a href="#Conversations">Conversations</a></li>
    </ul>
  </nav>
  <p id="followed"></p>
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
    document.getElementById("followed").textContent = here;
    document.querySelectorAll("[aria-label='Agent views'] a").forEach((link) => {
      if (link.textContent === here) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
  });
</script></html>`;

test.describe("navigation helpers on an Agent", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.setContent(FRAME);
  });

  test("Agent views are read from the tab row, not the breadcrumb's view switcher", async ({ page }) => {
    expect(await sectionNames(page, "Agent views")).toEqual(["Playground", "Versions", "Embed & limits", "Conversations"]);
    expect(await currentSection(page, "Agent views")).toBe("Playground");

    await openSection(page, "Agent views", "Versions");
    await expect(page.locator("#followed")).toHaveText("Versions");
    expect(await currentSection(page, "Agent views")).toBe("Versions");
  });

  test("the Agents switcher is the ▾ on the Agent's name", async ({ page }) => {
    await expect(menuButton(page, "Agents")).toHaveAccessibleName("HR helper, Agents");
    expect(await currentSection(page, "Agents")).toBe("HR helper");
    expect(await sectionNames(page, "Agents")).toEqual(["HR helper", "Pay helper"]);

    await openSection(page, "Agents", "Pay helper");
    await expect(page.locator("#followed")).toHaveText("Pay helper");
  });
});
