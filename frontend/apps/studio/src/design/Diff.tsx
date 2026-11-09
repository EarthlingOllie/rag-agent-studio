import { table } from "./recipes";

export type DiffLine =
  | { kind: "same"; text: string; before: number; after: number }
  | { kind: "removed"; text: string; before: number }
  | { kind: "added"; text: string; after: number };

const lines = (text: string) => (text === "" ? [] : text.split("\n"));

/** A line diff (longest common subsequence): removed lines come before the lines that replace them. */
export function diffLines(before: string, after: string): DiffLine[] {
  const a = lines(before);
  const b = lines(after);
  // common[i][j]: the longest common subsequence of a[i:] and b[j:].
  const common = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      const row = common[i] as number[];
      const below = common[i + 1] as number[];
      row[j] = a[i] === b[j] ? (below[j + 1] as number) + 1 : Math.max(below[j] as number, row[j + 1] as number);
    }
  }
  const result: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j]) {
      result.push({ kind: "same", text: a[i] as string, before: ++i, after: ++j });
    } else if (j >= b.length || (i < a.length && (common[i + 1]?.[j] as number) >= (common[i]?.[j + 1] as number))) {
      result.push({ kind: "removed", text: a[i] as string, before: ++i });
    } else {
      result.push({ kind: "added", text: b[j] as string, after: ++j });
    }
  }
  return result;
}

const ROW = { same: "", removed: "bg-danger-soft text-danger", added: "bg-accent-soft text-accent-ink" } as const;
const NUMBER = "w-10 px-2 py-0.5 text-right align-top text-muted select-none";

/**
 * What changed between two texts (a system prompt, Project Instructions, an Agent config), line
 * by line. Each side's line numbers are shown, and added and removed lines carry a + or − mark
 * and are read out as "Added" or "Removed", so the diff reads without colour.
 */
export function Diff({ label, before, after }: { label: string; before: string; after: string }) {
  const diff = diffLines(before, after);
  const added = diff.filter((line) => line.kind === "added").length;
  const removed = diff.filter((line) => line.kind === "removed").length;
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-muted">
        {added + removed === 0 ? "No changes" : `${String(added)} added, ${String(removed)} removed`}
      </p>
      <div className={table.wrap}>
        <table aria-label={label} className="w-full border-collapse font-mono text-[13px] leading-relaxed">
          <thead className="sr-only">
            <tr>
              <th scope="col">Line before</th>
              <th scope="col">Line after</th>
              <th scope="col">Change</th>
              <th scope="col">Text</th>
            </tr>
          </thead>
          <tbody>
            {diff.map((line, index) => (
              <tr key={index} className={ROW[line.kind]}>
                <td className={NUMBER}>{line.kind === "added" ? "" : line.before}</td>
                <td className={NUMBER}>{line.kind === "removed" ? "" : line.after}</td>
                <td className="w-6 py-0.5 text-center align-top select-none">
                  {line.kind !== "same" && (
                    <>
                      <span aria-hidden="true">{line.kind === "added" ? "+" : "−"}</span>
                      <span className="sr-only">{line.kind === "added" ? "Added" : "Removed"}</span>
                    </>
                  )}
                </td>
                <td className="py-0.5 pr-4 break-all whitespace-pre-wrap">
                  {line.kind === "added" ? (
                    <ins className="no-underline">{line.text}</ins>
                  ) : line.kind === "removed" ? (
                    <del className="no-underline">{line.text}</del>
                  ) : (
                    line.text
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
