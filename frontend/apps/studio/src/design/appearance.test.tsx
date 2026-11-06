import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import {
  APPEARANCE_KEY,
  applyAppearance,
  initAppearance,
  resetAppearanceForTests,
  setAppearance,
  useAppearance,
} from "./appearance";
import { AppearanceToggle } from "./TopBar";

function Probe() {
  const { appearance, resolved } = useAppearance();
  return <p>{`${appearance} → ${resolved}`}</p>;
}

/** A matchMedia whose dark preference the test can flip. */
function fakeSystem(prefersDark: boolean) {
  const listeners = new Set<() => void>();
  const media = {
    matches: prefersDark,
    addEventListener: (_type: string, listener: () => void) => listeners.add(listener),
    removeEventListener: (_type: string, listener: () => void) => listeners.delete(listener),
  };
  window.matchMedia = vi.fn(() => media) as unknown as typeof window.matchMedia;
  return {
    flip(next: boolean) {
      media.matches = next;
      act(() => {
        listeners.forEach((listener) => {
          listener();
        });
      });
    },
    listeners,
  };
}

beforeEach(() => {
  window.localStorage.clear();
  delete document.documentElement.dataset.appearance;
  resetAppearanceForTests();
});

afterEach(() => {
  // jsdom has no matchMedia of its own; remove the fake.
  Reflect.deleteProperty(window, "matchMedia");
});

it("follows the system until the Member chooses, and resolves through its preference", () => {
  const system = fakeSystem(false);
  const { unmount } = render(<Probe />);
  expect(screen.getByText("system → light")).toBeInTheDocument();
  system.flip(true);
  expect(screen.getByText("system → dark")).toBeInTheDocument();
  unmount();
  expect(system.listeners.size).toBe(0);
});

it("resolves the system to light when the browser can't say", () => {
  // jsdom has no matchMedia.
  render(<Probe />);
  expect(screen.getByText("system → light")).toBeInTheDocument();
});

it("remembers a choice, puts it on <html> and forgets it for system", () => {
  fakeSystem(false);
  render(<Probe />);
  act(() => {
    setAppearance("dark");
  });
  expect(screen.getByText("dark → dark")).toBeInTheDocument();
  expect(document.documentElement.dataset.appearance).toBe("dark");
  expect(window.localStorage.getItem(APPEARANCE_KEY)).toBe("dark");

  act(() => {
    setAppearance("system");
  });
  expect(document.documentElement.dataset.appearance).toBeUndefined();
  expect(window.localStorage.getItem(APPEARANCE_KEY)).toBeNull();
});

it("applies the remembered choice before the first render", () => {
  window.localStorage.setItem(APPEARANCE_KEY, "light");
  initAppearance();
  expect(document.documentElement.dataset.appearance).toBe("light");
  applyAppearance("system");
  expect(document.documentElement.dataset.appearance).toBeUndefined();
});

it("ignores a stored value it doesn't know", () => {
  window.localStorage.setItem(APPEARANCE_KEY, "sepia");
  fakeSystem(false);
  render(<Probe />);
  expect(screen.getByText("system → light")).toBeInTheDocument();
});

it("still works when storage is unavailable", () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  fakeSystem(false);
  render(<Probe />);
  expect(screen.getByText("system → light")).toBeInTheDocument();
  act(() => {
    setAppearance("dark");
  });
  expect(screen.getByText("dark → dark")).toBeInTheDocument();
});

it("toggles between light and dark from the top bar", async () => {
  fakeSystem(true);
  render(<AppearanceToggle />);
  await userEvent.click(screen.getByRole("button", { name: "Switch to light mode" }));
  expect(document.documentElement.dataset.appearance).toBe("light");
  await userEvent.click(screen.getByRole("button", { name: "Switch to dark mode" }));
  expect(document.documentElement.dataset.appearance).toBe("dark");
});
