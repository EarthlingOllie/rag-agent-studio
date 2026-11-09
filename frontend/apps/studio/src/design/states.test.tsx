import { render, screen } from "@testing-library/react";

import { EmptyState, Skeleton } from "./states";

it("says what is empty and what to do next", () => {
  render(
    <EmptyState
      icon="documents"
      title="No Documents yet"
      description="Upload a file to start the Knowledge Base."
      action={<button type="button">Upload</button>}
    />,
  );
  expect(screen.getByRole("heading", { name: "No Documents yet" })).toBeInTheDocument();
  expect(screen.getByText("Upload a file to start the Knowledge Base.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Upload" })).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it("announces an error state, and needs nothing but a title", () => {
  const { rerender } = render(<EmptyState tone="error" title="Couldn't load Conversations" description="Try again in a moment." />);
  expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load ConversationsTry again in a moment.");

  rerender(<EmptyState title="No matches" />);
  expect(screen.getByRole("heading", { name: "No matches" }).parentElement?.querySelectorAll("p, button, svg")).toHaveLength(0);
});

it("is a card's level-2 heading, or the page's h1 when it stands in for a whole page", () => {
  const { rerender } = render(<EmptyState title="No matches" />);
  expect(screen.getByRole("heading", { level: 2, name: "No matches" })).toBeInTheDocument();

  rerender(<EmptyState level={1} title="Project not found" />);
  expect(screen.getByRole("heading", { level: 1, name: "Project not found" })).toBeInTheDocument();
});

it("stands in for loading content and says it is loading", () => {
  const { rerender } = render(<Skeleton label="Loading Documents" lines={4} />);
  const skeleton = screen.getByRole("status", { name: "Loading Documents" });
  expect(skeleton).toHaveAttribute("aria-busy", "true");
  expect(skeleton.querySelectorAll("[data-skeleton-line]")).toHaveLength(4);

  rerender(<Skeleton />);
  expect(screen.getByRole("status", { name: "Loading" }).querySelectorAll("[data-skeleton-line]")).toHaveLength(3);
});
