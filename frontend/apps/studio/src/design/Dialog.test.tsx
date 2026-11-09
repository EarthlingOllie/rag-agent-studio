import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import { ConfirmDialog, Dialog } from "./Dialog";

function EditDetails({ withFields = true }: { withFields?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => { setOpen(true); }}>
        Edit details
      </button>
      <p>Behind the dialog</p>
      <Dialog
        open={open}
        title="Edit details"
        {...(withFields ? { description: "Name and describe the Project." } : {})}
        onClose={() => { setOpen(false); }}
        footer={withFields && <button type="button" onClick={() => { setOpen(false); }}>Save</button>}
      >
        {withFields ? (
          <label>
            Name <input defaultValue="Northwind Handbook" />
          </label>
        ) : (
          <p>Nothing to edit.</p>
        )}
      </Dialog>
    </>
  );
}

it("opens named and described, focuses its first control, and traps Tab inside", async () => {
  const user = userEvent.setup();
  render(<EditDetails />);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Edit details" }));
  const dialog = screen.getByRole("dialog", { name: "Edit details" });
  expect(dialog).toHaveAttribute("aria-modal", "true");
  expect(dialog).toHaveAccessibleDescription("Name and describe the Project.");
  expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();

  await user.tab();
  expect(screen.getByRole("textbox", { name: "Name" })).toHaveFocus();
  await user.tab();
  expect(screen.getByRole("button", { name: "Save" })).toHaveFocus();
  await user.tab();
  expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();
  await user.tab({ shift: true });
  expect(screen.getByRole("button", { name: "Save" })).toHaveFocus();
  await user.tab({ shift: true });
  expect(screen.getByRole("textbox", { name: "Name" })).toHaveFocus();
  await user.keyboard("x");
  expect(dialog).toBeInTheDocument();
});

it("closes on Escape, the Close button or a click on the scrim, and returns focus to the opener", async () => {
  const user = userEvent.setup();
  render(<EditDetails />);
  const opener = screen.getByRole("button", { name: "Edit details" });

  await user.click(opener);
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(opener).toHaveFocus();

  await user.click(opener);
  await user.click(screen.getByRole("button", { name: "Close" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(opener).toHaveFocus();

  await user.click(opener);
  await user.click(screen.getByRole("textbox", { name: "Name" }));
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  await user.click(screen.getByTestId("dialog-scrim"));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(opener).toHaveFocus();
});

it("keeps focus on the Close button when it is the only control", async () => {
  const user = userEvent.setup();
  render(<EditDetails withFields={false} />);
  await user.click(screen.getByRole("button", { name: "Edit details" }));
  expect(screen.getByRole("dialog", { name: "Edit details" })).not.toHaveAttribute("aria-describedby");
  expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
  await user.tab();
  await user.tab();
  expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();
});

function DeleteDocument({ destructive = true, onConfirm }: { destructive?: boolean; onConfirm: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => { setOpen(true); }}>
        Delete handbook.md
      </button>
      <ConfirmDialog
        open={open}
        title="Delete handbook.md?"
        confirmLabel="Delete"
        destructive={destructive}
        onConfirm={() => {
          onConfirm();
          setOpen(false);
        }}
        onCancel={() => { setOpen(false); }}
      >
        Its 42 chunks are removed and Agents stop citing it.
      </ConfirmDialog>
    </>
  );
}

it("asks for destructive confirmation as an alertdialog, focused on Cancel", async () => {
  const user = userEvent.setup();
  const onConfirm = vi.fn();
  render(<DeleteDocument onConfirm={onConfirm} />);
  const opener = screen.getByRole("button", { name: "Delete handbook.md" });

  await user.click(opener);
  const dialog = screen.getByRole("alertdialog", { name: "Delete handbook.md?" });
  expect(dialog).toHaveAccessibleDescription("Its 42 chunks are removed and Agents stop citing it.");
  expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
  // A destructive confirmation is not dismissed by a stray click outside it.
  await user.click(screen.getByTestId("dialog-scrim"));
  expect(dialog).toBeInTheDocument();

  await user.keyboard("{Escape}");
  expect(onConfirm).not.toHaveBeenCalled();
  expect(opener).toHaveFocus();

  await user.click(opener);
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  expect(onConfirm).not.toHaveBeenCalled();

  await user.click(opener);
  await user.click(screen.getByRole("button", { name: "Delete" }));
  expect(onConfirm).toHaveBeenCalledOnce();
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  expect(opener).toHaveFocus();
});

it("asks a non-destructive confirmation as a dialog that a scrim click cancels", async () => {
  const user = userEvent.setup();
  const onConfirm = vi.fn();
  render(<DeleteDocument destructive={false} onConfirm={onConfirm} />);
  await user.click(screen.getByRole("button", { name: "Delete handbook.md" }));
  expect(screen.getByRole("dialog", { name: "Delete handbook.md?" })).toBeInTheDocument();
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  await user.click(screen.getByTestId("dialog-scrim"));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(onConfirm).not.toHaveBeenCalled();
});

it("disables both buttons while the confirmed action runs, holding focus in the dialog", async () => {
  const user = userEvent.setup();
  render(
    <ConfirmDialog open title="Publish v3?" confirmLabel="Publish" busy onConfirm={vi.fn()} onCancel={vi.fn()}>
      Visitors get v3 at once.
    </ConfirmDialog>,
  );
  expect(screen.getByRole("button", { name: "Publish" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
  expect(screen.getByRole("dialog", { name: "Publish v3?" })).toHaveFocus();
  await user.tab();
  expect(screen.getByRole("dialog", { name: "Publish v3?" })).toHaveFocus();
});
