import { render, screen, within } from "@testing-library/react";

import { Breadcrumb, crumbLink } from "./Breadcrumb";

function path(names: string[], current: string) {
  return (
    <Breadcrumb>
      {names.map((name) => (
        <a key={name} href={`/${name}`} className={crumbLink} aria-current={name === current ? "page" : undefined}>
          {name}
        </a>
      ))}
    </Breadcrumb>
  );
}

it("lays its crumbs out as links in order, with separators hidden from assistive technology, and no menus", () => {
  render(path(["Northwind Handbook", "Agents", "HR helper"], "HR helper"));

  const nav = within(screen.getByRole("navigation", { name: "Breadcrumb" }));
  expect(nav.getAllByRole("listitem").map((item) => item.textContent)).toEqual(["Northwind Handbook", "/Agents", "/HR helper"]);
  expect(nav.getAllByRole("link").map((link) => link.textContent)).toEqual(["Northwind Handbook", "Agents", "HR helper"]);
  expect(nav.getByRole("link", { name: "HR helper" })).toHaveAttribute("aria-current", "page");
  expect(nav.getByRole("link", { name: "Agents" })).not.toHaveAttribute("aria-current");
  expect(nav.getAllByText("/").every((separator) => separator.getAttribute("aria-hidden") === "true")).toBe(true);
  expect(nav.queryAllByRole("button")).toEqual([]);
});

it("below md keeps only the last two crumbs, and the first of them loses its separator", () => {
  render(path(["Northwind Handbook", "Agents", "HR helper"], "HR helper"));

  // jsdom applies no stylesheet, so the breakpoint is read from the classes; the screenshots at 390 px show it.
  const [project, section, agent] = screen.getAllByRole("listitem") as [HTMLElement, HTMLElement, HTMLElement];
  expect(project).toHaveClass("hidden", "md:flex");
  expect(section).not.toHaveClass("hidden");
  expect(agent).not.toHaveClass("hidden");
  expect(within(section).getByText("/")).toHaveClass("hidden", "md:inline");
  expect(within(agent).getByText("/")).not.toHaveClass("hidden");
});

it("hides nothing when there are two crumbs or fewer", () => {
  render(path(["Settings", "Members"], "Members"));

  expect(screen.getAllByRole("listitem").filter((item) => item.classList.contains("hidden"))).toEqual([]);
});
