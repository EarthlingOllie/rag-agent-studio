import { render, screen, within } from "@testing-library/react";

import { Diff, diffLines } from "./Diff";

const V1 = ["You are the HR helper.", "Answer from the handbook.", "Be brief."].join("\n");
const V2 = ["You are the HR helper.", "Answer only from the handbook.", "Be brief.", "Cite your sources."].join("\n");

/** Each row's cells as text: old line number, new line number, mark, line. */
function rows() {
  return within(screen.getByRole("table", { name: "System prompt, v1 to v2" }))
    .getAllByRole("row")
    .slice(1)
    .map((row) => within(row).getAllByRole("cell").map((cell) => cell.textContent));
}

it("numbers both sides' lines and marks added and removed lines with + and −, not only colour", () => {
  render(<Diff label="System prompt, v1 to v2" before={V1} after={V2} />);
  expect(rows()).toEqual([
    ["1", "1", "", "You are the HR helper."],
    ["2", "", "−Removed", "Answer from the handbook."],
    ["", "2", "+Added", "Answer only from the handbook."],
    ["3", "3", "", "Be brief."],
    ["", "4", "+Added", "Cite your sources."],
  ]);
  expect(screen.getByText("Answer from the handbook.").tagName).toBe("DEL");
  expect(screen.getByText("Cite your sources.").tagName).toBe("INS");
  expect(screen.getByText("Cite your sources.").closest("tr")?.className).toContain("bg-accent-soft");
  expect(screen.getByText("Answer from the handbook.").closest("tr")?.className).toContain("bg-danger-soft");
  expect(screen.getByText("2 added, 1 removed")).toBeInTheDocument();
});

it("says when nothing changed", () => {
  render(<Diff label="System prompt, v1 to v2" before={V1} after={V1} />);
  expect(screen.getByText("No changes")).toBeInTheDocument();
  expect(rows()).toHaveLength(3);
});

it("diffs from and to nothing", () => {
  expect(diffLines("", "a")).toEqual([{ kind: "added", text: "a", after: 1 }]);
  expect(diffLines("a\nb", "")).toEqual([
    { kind: "removed", text: "a", before: 1 },
    { kind: "removed", text: "b", before: 2 },
  ]);
  expect(diffLines("", "")).toEqual([]);
});
