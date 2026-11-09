import { render, screen } from "@testing-library/react";

import { Meter } from "./Meter";

function fill(name: string) {
  return screen.getByRole("meter", { name }).firstElementChild as HTMLElement;
}

it("is a named meter that always prints its value", () => {
  render(<Meter label="Token Budget" value={4200} max={10000} unit="tokens" />);
  const meter = screen.getByRole("meter", { name: "Token Budget" });
  expect(meter).toHaveAttribute("aria-valuenow", "4200");
  expect(meter).toHaveAttribute("aria-valuemin", "0");
  expect(meter).toHaveAttribute("aria-valuemax", "10000");
  expect(meter).toHaveAttribute("aria-valuetext", "4,200 of 10,000 tokens");
  expect(screen.getByText("4,200 / 10,000 tokens")).toBeInTheDocument();
  expect(fill("Token Budget").style.width).toBe("42%");
});

it("uses the accent under 80%, the flag colour from 80% and the danger colour when spent", () => {
  render(
    <>
      <Meter label="Under" value={79} max={100} />
      <Meter label="Near" value={80} max={100} />
      <Meter label="Spent" value={100} max={100} />
      <Meter label="Over" value={130} max={100} />
    </>,
  );
  expect(fill("Under").className).toContain("bg-accent");
  expect(fill("Near").className).toContain("bg-flag");
  expect(fill("Spent").className).toContain("bg-danger");
  expect(fill("Over").className).toContain("bg-danger");
  // Overspend fills the bar but no further, and the true value is still printed.
  expect(fill("Over").style.width).toBe("100%");
  expect(screen.getByText("130 / 100")).toBeInTheDocument();
});

it("prints values in the caller's format", () => {
  render(<Meter label="Spend" value={12.5} max={50} format={(n) => `USD ${n.toFixed(2)}`} />);
  expect(screen.getByText("USD 12.50 / USD 50.00")).toBeInTheDocument();
  expect(screen.getByRole("meter", { name: "Spend" })).toHaveAttribute("aria-valuetext", "USD 12.50 of USD 50.00");
});
