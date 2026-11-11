import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CodeBlock, COPIED_FOR_MS } from "./CodeBlock";

const SNIPPET = '<script src="https://studio.example/embed.js" data-agent="ag_123" async></script>';

it("shows the code and copies exactly that text, confirming it", async () => {
  const user = userEvent.setup();
  render(<CodeBlock label="Embed snippet" code={SNIPPET} />);
  expect(screen.getByText(SNIPPET).tagName).toBe("CODE");
  // A long line scrolls sideways, so the box takes keyboard focus (WCAG 2.1.1).
  expect(screen.getByRole("region", { name: "Embed snippet code" })).toHaveAttribute("tabindex", "0");

  await user.click(screen.getByRole("button", { name: "Copy Embed snippet" }));
  expect(await navigator.clipboard.readText()).toBe(SNIPPET);
  // The name starts with the visible text, so "Copied" is in it too (WCAG 2.5.3, Label in Name).
  expect(screen.getByRole("button", { name: "Copied Embed snippet" })).toHaveTextContent("Copied");
  expect(screen.getByRole("status")).toHaveTextContent("Embed snippet copied.");
});

it("says so when the browser refuses to copy", async () => {
  const user = userEvent.setup();
  render(<CodeBlock label="Embed snippet" code={SNIPPET} />);
  vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("denied"));
  await user.click(screen.getByRole("button", { name: "Copy Embed snippet" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't copy. Select the text and copy it instead.");
  expect(screen.getByRole("button", { name: "Copy Embed snippet" })).toHaveTextContent("Copy");
});

it("goes back to Copy after a moment", async () => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  try {
    Object.defineProperty(navigator, "clipboard", { value: { writeText: vi.fn().mockResolvedValue(undefined) }, configurable: true });
    render(<CodeBlock label="Embed snippet" code={SNIPPET} />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Copy Embed snippet" }));
      await Promise.resolve();
    });
    expect(screen.getByRole("button", { name: "Copied Embed snippet" })).toHaveTextContent("Copied");
    act(() => {
      vi.advanceTimersByTime(COPIED_FOR_MS);
    });
    expect(screen.getByRole("button", { name: "Copy Embed snippet" })).toHaveTextContent(/^Copy$/);
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  } finally {
    vi.useRealTimers();
  }
});
