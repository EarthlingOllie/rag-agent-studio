import { render, screen } from "@testing-library/react";

import { Badge, BADGE_LABELS, type BadgeKind } from "./Badge";

it.each([
  ["live", "Live"],
  ["current", "Current"],
  ["draft", "Draft"],
  ["notLive", "Not live"],
  ["archived", "Archived"],
  ["instructionsBehind", "Instructions behind"],
  ["budgetSpent", "Budget spent"],
  ["blocked", "Blocked by guardrail"],
  ["lowSample", "Low sample"],
  ["flagged", "Flagged"],
  ["checkPassed", "Working"],
  ["checkFailed", "Check failed"],
] satisfies [BadgeKind, string][])("labels the %s badge %s", (kind, label) => {
  render(<Badge kind={kind} />);
  expect(screen.getByText(label)).toBeInTheDocument();
  expect(BADGE_LABELS[kind]).toBe(label);
});

it("colours a badge by what it means: Live in the accent, warnings in flag, blocks in danger", () => {
  render(
    <>
      <Badge kind="live" />
      <Badge kind="draft" />
      <Badge kind="instructionsBehind" />
      <Badge kind="budgetSpent" />
      <Badge kind="archived" />
      <Badge kind="flagged" />
    </>,
  );
  expect(screen.getByText("Live").className).toContain("bg-accent-soft");
  expect(screen.getByText("Draft").className).toContain("bg-sand");
  expect(screen.getByText("Instructions behind").className).toContain("bg-flag-soft");
  expect(screen.getByText("Budget spent").className).toContain("bg-danger-soft");
  expect(screen.getByText("Archived").className).toContain("bg-sunken");
  expect(screen.getByText("Flagged").className).toContain("bg-flag-soft");
});

it("explains a badge on hover when given a reason", () => {
  render(<Badge kind="lowSample" title="Fewer than 30 rated answers" />);
  expect(screen.getByText("Low sample")).toHaveAttribute("title", "Fewer than 30 rated answers");
});

it("shows a Version as a mono chip read out in full", () => {
  render(<Badge kind="version" version={3} />);
  const chip = screen.getByLabelText("Version 3");
  expect(chip).toHaveTextContent("v3");
  expect(chip.className).toContain("font-mono");
});
