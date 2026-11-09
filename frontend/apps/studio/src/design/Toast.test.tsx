import { act, fireEvent, render, screen } from "@testing-library/react";

import { TOAST_DURATION_MS, ToastProvider, useToast } from "./Toast";

function ArchiveButton({ onUndo }: { onUndo?: () => void }) {
  const toast = useToast();
  return (
    <>
      <button
        type="button"
        onClick={() => {
          toast.show("Archived HR helper.", onUndo === undefined ? {} : { onUndo });
        }}
      >
        Archive
      </button>
      <button
        type="button"
        onClick={() => {
          toast.show("Saved.");
        }}
      >
        Save
      </button>
    </>
  );
}

// Clicks are fireEvent: user-event and Testing Library wait on setTimeout, which is faked here.
beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
});
afterEach(() => {
  vi.useRealTimers();
});

it("announces a confirmation politely, from a live region that was there before it", () => {
  render(
    <ToastProvider>
      <ArchiveButton />
    </ToastProvider>,
  );
  const region = screen.getByRole("status");
  expect(region).toHaveAttribute("aria-live", "polite");
  expect(region).toBeEmptyDOMElement();

  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(region).toHaveTextContent("Saved.");
  expect(screen.queryByRole("button", { name: "Undo" })).not.toBeInTheDocument();

  act(() => {
    vi.advanceTimersByTime(TOAST_DURATION_MS);
  });
  expect(region).toBeEmptyDOMElement();
});

it("offers Undo, which runs once and dismisses the toast", () => {
  const onUndo = vi.fn();
  render(
    <ToastProvider>
      <ArchiveButton onUndo={onUndo} />
    </ToastProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Archive" }));
  expect(screen.getByRole("status")).toHaveTextContent("Archived HR helper.");

  fireEvent.click(screen.getByRole("button", { name: "Undo" }));
  expect(onUndo).toHaveBeenCalledOnce();
  expect(screen.getByRole("status")).toBeEmptyDOMElement();
});

it("keeps the newest toast, and can be dismissed by hand", () => {
  render(
    <ToastProvider>
      <ArchiveButton onUndo={vi.fn()} />
    </ToastProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Archive" }));
  act(() => {
    vi.advanceTimersByTime(TOAST_DURATION_MS - 1000);
  });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(screen.getByRole("status")).toHaveTextContent("Saved.");
  expect(screen.getByRole("status")).not.toHaveTextContent("Archived");
  // The first toast's timer does not cut the second one short.
  act(() => {
    vi.advanceTimersByTime(2000);
  });
  expect(screen.getByRole("status")).toHaveTextContent("Saved.");

  fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
  expect(screen.getByRole("status")).toBeEmptyDOMElement();
});

it("needs a ToastProvider", () => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  expect(() => render(<ArchiveButton />)).toThrow("useToast needs a ToastProvider");
});
