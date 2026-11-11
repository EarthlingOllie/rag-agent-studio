import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import { EditableList } from "./EditableList";

function Origins({ initial, onChange = vi.fn() }: { initial: string[]; onChange?: (items: string[]) => void }) {
  const [items, setItems] = useState(initial);
  return (
    <EditableList
      label="Allowed Origins"
      inputLabel="New origin"
      placeholder="https://example.com"
      items={items}
      onChange={(next) => {
        setItems(next);
        onChange(next);
      }}
      validate={(value) => (value.startsWith("https://") ? undefined : "Use an https:// origin.")}
      emptyWarning="No site can embed this Agent until you add an origin."
    />
  );
}

const listed = () => within(screen.getByRole("list", { name: "Allowed Origins" })).queryAllByRole("listitem").map((item) => item.textContent);

it("adds with Enter or the Add button, trimming, and clears the input", async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  render(<Origins initial={["https://shop.example"]} onChange={onChange} />);
  expect(listed()).toEqual(["https://shop.example"]);

  await user.type(screen.getByRole("textbox", { name: "New origin" }), "  https://help.example {Enter}");
  expect(listed()).toEqual(["https://shop.example", "https://help.example"]);
  expect(screen.getByRole("textbox", { name: "New origin" })).toHaveValue("");
  expect(screen.getByRole("textbox", { name: "New origin" })).toHaveFocus();

  await user.type(screen.getByRole("textbox", { name: "New origin" }), "https://docs.example");
  await user.click(screen.getByRole("button", { name: "Add" }));
  expect(onChange).toHaveBeenLastCalledWith(["https://shop.example", "https://help.example", "https://docs.example"]);
});

it("refuses blanks, duplicates and invalid values, saying why, until the value changes", async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  render(<Origins initial={["https://shop.example"]} onChange={onChange} />);
  const input = screen.getByRole("textbox", { name: "New origin" });

  await user.type(input, "   {Enter}");
  expect(onChange).not.toHaveBeenCalled();
  expect(input).not.toHaveAttribute("aria-invalid", "true");

  await user.type(input, "https://shop.example{Enter}");
  expect(input).toHaveAttribute("aria-invalid", "true");
  expect(input).toHaveAccessibleDescription("Already in the list.");

  await user.clear(input);
  expect(input).not.toHaveAttribute("aria-invalid", "true");
  await user.type(input, "http://plain.example{Enter}");
  expect(input).toHaveAccessibleDescription("Use an https:// origin.");
  expect(onChange).not.toHaveBeenCalled();

  await user.keyboard("{Escape}");
  expect(input).toHaveValue("");
  expect(input).not.toHaveAttribute("aria-invalid", "true");
});

it("removes an item, moving focus to the next Remove button, the previous one, then the input", async () => {
  const user = userEvent.setup();
  render(<Origins initial={["https://a.example", "https://b.example", "https://c.example"]} />);

  await user.click(screen.getByRole("button", { name: "Remove https://b.example" }));
  expect(listed()).toEqual(["https://a.example", "https://c.example"]);
  expect(screen.getByRole("button", { name: "Remove https://c.example" })).toHaveFocus();

  await user.keyboard("{Enter}");
  expect(screen.getByRole("button", { name: "Remove https://a.example" })).toHaveFocus();
  await user.keyboard(" ");
  expect(screen.getByRole("textbox", { name: "New origin" })).toHaveFocus();
});

it("warns when the list is empty", async () => {
  const user = userEvent.setup();
  render(<Origins initial={["https://a.example"]} />);
  expect(screen.queryByText("No site can embed this Agent until you add an origin.")).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Remove https://a.example" }));
  expect(listed()).toEqual([]);
  expect(screen.getByRole("status")).toHaveTextContent("No site can embed this Agent until you add an origin.");
});

it("needs no validation or warning, and does not submit the form it sits in", async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  const onSubmit = vi.fn((event: SubmitEvent) => {
    event.preventDefault();
  });
  render(
    <form onSubmit={(event) => { onSubmit(event.nativeEvent); }}>
      <EditableList label="Stop words" inputLabel="New word" items={[]} onChange={onChange} />
    </form>,
  );
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  await user.type(screen.getByRole("textbox", { name: "New word" }), "anything{Enter}");
  expect(onChange).toHaveBeenCalledWith(["anything"]);
  await user.click(screen.getByRole("button", { name: "Add" }));
  expect(onSubmit).not.toHaveBeenCalled();
});
