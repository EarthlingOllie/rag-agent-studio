import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { Breadcrumb, crumbClass, CrumbSwitcher, CrumbText } from "./Breadcrumb";
import { Icon } from "./Icon";
import { Menu, type MenuItem } from "./Menu";
import { button } from "./recipes";

function sections(onSelect: (label: string) => void): MenuItem[] {
  return [
    { label: "Documents", icon: "documents", hint: "1", current: true, onSelect: () => {
      onSelect("Documents");
    } },
    { label: "Instructions", icon: "instructions", hint: "2", onSelect: () => {
      onSelect("Instructions");
    } },
    { label: "Agents", id: "agents", onSelect: () => {
      onSelect("Agents");
    } },
  ];
}

it("opens on the current item, moves with the arrow keys, wraps, and selects", async () => {
  const user = userEvent.setup();
  const onSelect = vi.fn();
  render(<Menu label="Documents" items={sections(onSelect)} triggerClassName={button.ghost} />);

  const trigger = screen.getByRole("button", { name: "Documents" });
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  await user.click(trigger);
  expect(trigger).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByRole("menu")).toHaveAttribute("id", trigger.getAttribute("aria-controls"));
  expect(screen.getByRole("menuitem", { name: /Documents/ })).toHaveFocus();
  expect(screen.getByRole("menuitem", { name: /Documents/ })).toHaveAttribute("aria-current", "page");

  await user.keyboard("{ArrowDown}");
  expect(screen.getByRole("menuitem", { name: /Instructions/ })).toHaveFocus();
  await user.keyboard("{ArrowDown}{ArrowDown}");
  expect(screen.getByRole("menuitem", { name: /Documents/ })).toHaveFocus();
  await user.keyboard("{ArrowUp}");
  expect(screen.getByRole("menuitem", { name: "Agents" })).toHaveFocus();
  await user.keyboard("{Home}");
  expect(screen.getByRole("menuitem", { name: /Documents/ })).toHaveFocus();
  await user.keyboard("{End}");
  expect(screen.getByRole("menuitem", { name: "Agents" })).toHaveFocus();
  await user.keyboard("a");
  expect(screen.getByRole("menu")).toBeInTheDocument();

  await user.keyboard("{Enter}");
  expect(onSelect).toHaveBeenCalledWith("Agents");
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
});

it("opens from the keyboard and closes with Escape, Tab, a second click or a click outside", async () => {
  const user = userEvent.setup();
  render(
    <>
      <Menu label="Documents" items={sections(vi.fn())} triggerClassName={button.ghost} />
      <p>Outside</p>
    </>,
  );
  const trigger = screen.getByRole("button", { name: "Documents" });

  trigger.focus();
  await user.keyboard("{ArrowUp}");
  expect(screen.getByRole("menu")).toBeInTheDocument();
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
  await user.keyboard("x");
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();

  await user.keyboard("{ArrowDown}");
  await user.keyboard("{Tab}");
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();

  await user.keyboard("x");
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();

  await user.click(trigger);
  await user.click(screen.getByRole("menu"));
  expect(screen.getByRole("menu")).toBeInTheDocument();
  await user.click(trigger);
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();

  await user.click(trigger);
  await user.click(screen.getByText("Outside"));
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
});

it("names an icon-only trigger, aligns to the end, skips disabled items and marks danger", async () => {
  const user = userEvent.setup();
  const onDelete = vi.fn();
  render(
    <Menu
      label={<Icon name="more" />}
      triggerLabel="Actions for handbook.md"
      align="end"
      triggerClassName={button.iconBare}
      items={[
        { label: "Retry", disabled: true, onSelect: vi.fn() },
        { label: "Delete", danger: true, onSelect: onDelete },
      ]}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Actions for handbook.md" }));
  expect(screen.getByRole("menu").className).toContain("right-0");
  expect(screen.getByRole("menuitem", { name: "Retry" })).toBeDisabled();
  expect(screen.getByRole("menuitem", { name: "Delete" })).toHaveFocus();
  expect(screen.getByRole("menuitem", { name: "Delete" }).className).toContain("text-danger");
  await user.click(screen.getByRole("menuitem", { name: "Delete" }));
  expect(onDelete).toHaveBeenCalledOnce();
});

it("does nothing with the arrow keys when every item is disabled", async () => {
  const user = userEvent.setup();
  render(<Menu label="Nothing" triggerClassName={button.ghost} items={[{ label: "Retry", disabled: true, onSelect: vi.fn() }]} />);
  await user.click(screen.getByRole("button", { name: "Nothing" }));
  await user.keyboard("{ArrowDown}");
  expect(screen.getByRole("menu")).toBeInTheDocument();
});

it("lays crumbs out with separators; the current one is the accent and says so", async () => {
  const user = userEvent.setup();
  const onSelect = vi.fn();
  render(
    <Breadcrumb>
      <a href="/" className={crumbClass()}>
        Northwind Traders
      </a>
      <CrumbSwitcher
        label="Northwind Handbook"
        menuLabel="Projects"
        items={[{ label: "Northwind Handbook", current: true, onSelect: vi.fn() }]}
      />
      <CrumbSwitcher label="Documents" menuLabel="Project sections" current items={sections(onSelect)} />
    </Breadcrumb>,
  );
  const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
  expect(nav.querySelectorAll("li")).toHaveLength(3);
  expect(nav.textContent).toBe("Northwind Traders/Northwind Handbook/Documents");

  const current = screen.getByRole("button", { name: "Documents, Project sections" });
  expect(current).toHaveAttribute("aria-current", "page");
  expect(current.className).toContain("text-accent");
  const project = screen.getByRole("button", { name: "Northwind Handbook, Projects" });
  expect(project).not.toHaveAttribute("aria-current");
  expect(project.className).toContain("text-muted");

  await user.click(current);
  expect(screen.getByRole("menu", { name: "Project sections" })).toBeInTheDocument();
  await user.click(screen.getByRole("menuitem", { name: /Instructions/ }));
  expect(onSelect).toHaveBeenCalledWith("Instructions");
});

it("shows a crumb with nothing to switch to as text", () => {
  render(
    <>
      <CrumbText current>HR helper</CrumbText>
      <CrumbText>Archived</CrumbText>
    </>,
  );
  expect(screen.getByText("HR helper")).toHaveAttribute("aria-current", "page");
  expect(screen.getByText("Archived")).not.toHaveAttribute("aria-current");
});

it("renders destinations as links that close the menu when followed", async () => {
  const user = userEvent.setup();
  render(
    <Menu
      label="Documents"
      triggerClassName={button.ghost}
      items={[
        { label: "Documents", current: true, renderLink: (props) => <a href="#documents" {...props} /> },
        { label: "Agents", renderLink: (props) => <a href="#agents" {...props} /> },
      ]}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Documents" }));
  const current = screen.getByRole("menuitem", { name: "Documents" });
  expect(current).toHaveAttribute("href", "#documents");
  expect(current).toHaveAttribute("aria-current", "page");
  expect(current).toHaveFocus();
  await user.keyboard("{ArrowDown}");
  expect(screen.getByRole("menuitem", { name: "Agents" })).toHaveFocus();
  await user.keyboard("{Enter}");
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  expect(window.location.hash).toBe("#agents");
});
