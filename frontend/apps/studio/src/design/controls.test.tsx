import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import { BulkBar, Pagination, Segmented } from "./controls";

const SOURCES = [
  { value: "visitors", label: "Visitors" },
  { value: "playground", label: "Playground" },
  { value: "all", label: "All" },
];

function Source({ onChange }: { onChange: (value: string) => void }) {
  const [value, setValue] = useState("visitors");
  return (
    <Segmented
      label="Source"
      options={SOURCES}
      value={value}
      onChange={(next) => {
        setValue(next);
        onChange(next);
      }}
    />
  );
}

describe("Segmented", () => {
  it("is a radio group with one tab stop, on the chosen option", async () => {
    const user = userEvent.setup();
    render(
      <>
        <button type="button">Before</button>
        <Source onChange={vi.fn()} />
      </>,
    );
    expect(screen.getByRole("radiogroup", { name: "Source" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Visitors" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Playground" })).not.toBeChecked();

    await user.click(screen.getByRole("button", { name: "Before" }));
    await user.tab();
    expect(screen.getByRole("radio", { name: "Visitors" })).toHaveFocus();
    await user.tab();
    expect(document.body).toHaveFocus();
  });

  it("moves and chooses with the arrow keys, wrapping, and jumps with Home and End", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Source onChange={onChange} />);
    screen.getByRole("radio", { name: "Visitors" }).focus();

    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("radio", { name: "Playground" })).toHaveFocus();
    expect(screen.getByRole("radio", { name: "Playground" })).toBeChecked();
    await user.keyboard("{ArrowDown}{ArrowDown}");
    expect(screen.getByRole("radio", { name: "Visitors" })).toBeChecked();
    await user.keyboard("{ArrowLeft}");
    expect(screen.getByRole("radio", { name: "All" })).toBeChecked();
    await user.keyboard("{ArrowUp}");
    expect(screen.getByRole("radio", { name: "Playground" })).toBeChecked();
    await user.keyboard("{Home}");
    expect(screen.getByRole("radio", { name: "Visitors" })).toHaveFocus();
    await user.keyboard("{End}");
    expect(screen.getByRole("radio", { name: "All" })).toHaveFocus();
    await user.keyboard("a");
    expect(screen.getByRole("radio", { name: "All" })).toHaveFocus();
    expect(onChange.mock.calls.map(([value]) => value as string)).toEqual(["playground", "all", "visitors", "all", "playground", "visitors", "all"]);

    await user.click(screen.getByRole("radio", { name: "Playground" }));
    expect(screen.getByRole("radio", { name: "Playground" })).toBeChecked();
  });
});

function Pages({ initial, pageCount }: { initial: number; pageCount: number }) {
  const [page, setPage] = useState(initial);
  return <Pagination label="Conversations pages" page={page} pageCount={pageCount} onPageChange={setPage} />;
}

/** The page buttons' text, with "…" for a gap. */
function pages() {
  return Array.from(screen.getByRole("navigation", { name: "Conversations pages" }).querySelectorAll("li")).map(
    (item) => item.textContent,
  );
}

describe("Pagination", () => {
  it("pages with Previous, Next and page numbers, marking the current page", async () => {
    const user = userEvent.setup();
    render(<Pages initial={1} pageCount={3} />);
    expect(pages()).toEqual(["1", "2", "3"]);
    expect(screen.getByRole("button", { name: "Page 1" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByRole("button", { name: "Page 2" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "Page 1" })).not.toHaveAttribute("aria-current");
    await user.click(screen.getByRole("button", { name: "Page 3" }));
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Previous page" }));
    expect(screen.getByRole("button", { name: "Page 2" })).toHaveAttribute("aria-current", "page");
  });

  it("shortens long runs of pages around the first, current and last", () => {
    const { rerender } = render(<Pages initial={6} pageCount={20} />);
    expect(pages()).toEqual(["1", "…", "5", "6", "7", "…", "20"]);
    rerender(<Pagination label="Conversations pages" page={2} pageCount={20} onPageChange={vi.fn()} />);
    expect(pages()).toEqual(["1", "2", "3", "…", "20"]);
    rerender(<Pagination label="Conversations pages" page={20} pageCount={20} onPageChange={vi.fn()} />);
    expect(pages()).toEqual(["1", "…", "19", "20"]);
    rerender(<Pagination label="Conversations pages" page={1} pageCount={20} onPageChange={vi.fn()} />);
    expect(pages()).toEqual(["1", "2", "…", "20"]);
    // A gap of a single page shows that page rather than "…".
    rerender(<Pagination label="Conversations pages" page={4} pageCount={20} onPageChange={vi.fn()} />);
    expect(pages()).toEqual(["1", "2", "3", "4", "5", "…", "20"]);
  });

  it("is not shown for a single page", () => {
    render(<Pagination label="Conversations pages" page={1} pageCount={1} onPageChange={vi.fn()} />);
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });
});

describe("BulkBar", () => {
  function Bar({ count, onClear = vi.fn(), onPublish = vi.fn() }: { count: number; onClear?: () => void; onPublish?: () => void }) {
    return (
      <BulkBar count={count} noun={["Agent", "Agents"]} onClear={onClear}>
        <button type="button" onClick={onPublish}>
          Publish
        </button>
        <button type="button">Archive</button>
      </BulkBar>
    );
  }

  it("appears with a selection, says how many, and offers its actions", async () => {
    const user = userEvent.setup();
    const onPublish = vi.fn();
    const { rerender } = render(<Bar count={0} onPublish={onPublish} />);
    expect(screen.queryByRole("toolbar")).not.toBeInTheDocument();

    rerender(<Bar count={1} onPublish={onPublish} />);
    expect(screen.getByRole("toolbar", { name: "Bulk actions" })).toHaveTextContent("1 Agent selected");
    expect(screen.getByRole("status")).toHaveTextContent("1 Agent selected");
    rerender(<Bar count={3} onPublish={onPublish} />);
    expect(screen.getByRole("toolbar", { name: "Bulk actions" })).toHaveTextContent("3 Agents selected");
    await user.click(screen.getByRole("button", { name: "Publish" }));
    expect(onPublish).toHaveBeenCalledOnce();
  });

  it("moves between its buttons with the arrow keys and clears with Escape or Clear selection", async () => {
    const user = userEvent.setup();
    const onClear = vi.fn();
    render(<Bar count={2} onClear={onClear} />);
    screen.getByRole("button", { name: "Publish" }).focus();

    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("button", { name: "Archive" })).toHaveFocus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("button", { name: "Clear selection" })).toHaveFocus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("button", { name: "Publish" })).toHaveFocus();
    await user.keyboard("{ArrowLeft}");
    expect(screen.getByRole("button", { name: "Clear selection" })).toHaveFocus();
    await user.keyboard("{Home}");
    expect(screen.getByRole("button", { name: "Publish" })).toHaveFocus();
    await user.keyboard("{End}");
    expect(screen.getByRole("button", { name: "Clear selection" })).toHaveFocus();
    await user.keyboard("b");
    expect(onClear).not.toHaveBeenCalled();

    await user.keyboard("{Escape}");
    expect(onClear).toHaveBeenCalledOnce();
    await user.click(screen.getByRole("button", { name: "Clear selection" }));
    expect(onClear).toHaveBeenCalledTimes(2);
  });
});
