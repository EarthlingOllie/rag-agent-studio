import { render, screen } from "@testing-library/react";

import { FlagCount, Notice, PageHeader, Section, StatCard, Status, Tag } from "./content";
import { Icon, WaveMark } from "./Icon";
import { Avatar, Brand, TopBar } from "./TopBar";

it("heads a page with a title, description and actions, each optional but the title", () => {
  const { rerender } = render(
    <PageHeader title="Northwind Handbook" description="Staff handbook." actions={<button type="button">Edit details</button>} />,
  );
  expect(screen.getByRole("heading", { level: 1, name: "Northwind Handbook" })).toBeInTheDocument();
  expect(screen.getByText("Staff handbook.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Edit details" })).toBeInTheDocument();

  rerender(<PageHeader title="Projects" />);
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 1 }).parentElement?.querySelector("p")).toBeNull();
});

it("heads a section inside a page at level 2, so the page keeps its one h1", () => {
  render(<PageHeader level={2} title="Agents" actions={<button type="button">New Agent</button>} />);
  expect(screen.getByRole("heading", { level: 2, name: "Agents" })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
});

it("shows a stat with an optional unit, in the flag colour when asked", () => {
  render(
    <>
      <StatCard label="Documents" value={4} unit="/ 500" />
      <StatCard label="Flagged chunks" value={2} tone="flag" />
    </>,
  );
  expect(screen.getByText("Documents").nextElementSibling?.textContent).toBe("4 / 500");
  const flagged = screen.getByText("Flagged chunks").nextElementSibling;
  expect(flagged?.textContent).toBe("2");
  expect(flagged?.className).toContain("text-flag");
  expect(screen.getByText("Documents").nextElementSibling?.className).toContain("text-ink");
});

it("labels Tags, statuses and flag counts", () => {
  render(
    <>
      <Tag>Products</Tag>
      <Status tone="ready">Ready</Status>
      <Status tone="failed">Failed</Status>
      <FlagCount count={0} label="flagged chunks" />
      <FlagCount count={2} label="flagged chunks" />
    </>,
  );
  expect(screen.getByText("Products").className).toContain("bg-sand");
  expect(screen.getByText("Ready").firstElementChild?.className).toContain("bg-accent");
  expect(screen.getByText("Failed").firstElementChild?.className).toContain("bg-danger");
  expect(screen.getByLabelText("No flagged chunks")).toHaveTextContent("—");
  expect(screen.getByLabelText("2 flagged chunks")).toHaveTextContent("2");
});

it("announces errors and keeps other notices polite", () => {
  render(
    <>
      <Notice tone="error">The upload failed.</Notice>
      <Notice tone="success">Published.</Notice>
    </>,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("The upload failed.");
  expect(screen.getByRole("status")).toHaveTextContent("Published.");
});

it("collapses a settings section and summarises it", () => {
  render(
    <>
      <Section title="Behaviour" defaultOpen>
        <p>System prompt</p>
      </Section>
      <Section title="Retrieval" summary="top-5 · hybrid 0.5">
        <p>Chunks per answer</p>
      </Section>
    </>,
  );
  expect(screen.getByText("Behaviour").closest("details")).toHaveAttribute("open");
  expect(screen.getByText("Retrieval").closest("details")).not.toHaveAttribute("open");
  expect(screen.getByText("top-5 · hybrid 0.5")).toBeInTheDocument();
});

it("frames the Studio with a top bar, brand and avatar", () => {
  const { rerender } = render(
    <TopBar home={<Brand />} breadcrumb={<nav aria-label="Breadcrumb" />} actions={<Avatar name="Nadia  Novak" />} />,
  );
  expect(screen.getByRole("banner")).toHaveTextContent("Studio");
  expect(screen.getByRole("navigation", { name: "Breadcrumb" })).toBeInTheDocument();
  expect(screen.getByRole("img", { name: "Nadia Novak" })).toHaveTextContent("NN");

  rerender(<TopBar home={<Brand />} />);
  expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
});

it("draws icons and the mark, decoratively", () => {
  const { container } = render(
    <>
      <Icon name="more" />
      <Icon name="search" size={20} className="text-muted" />
      <WaveMark size={24} />
    </>,
  );
  const svgs = container.querySelectorAll("svg");
  expect(svgs).toHaveLength(3);
  svgs.forEach((svg) => {
    expect(svg).toHaveAttribute("aria-hidden", "true");
  });
  expect(svgs[0]?.querySelectorAll("circle")).toHaveLength(3);
  expect(svgs[1]).toHaveAttribute("width", "20");
  expect(svgs[2]).toHaveAttribute("width", "24");
});
