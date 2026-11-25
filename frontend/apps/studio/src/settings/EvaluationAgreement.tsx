import type { Schemas } from "@studio/api-client";
import { Link } from "@tanstack/react-router";
import { useId } from "react";

import { Badge, table, text } from "../design";
import { useEvaluationAgreement } from "../reviews/reviews";
import { judgingSetupLabel } from "./models";

type Figures = Omit<Schemas["CheckAgreementOut"], "check">;
type Agreement = Schemas["AgreementOut"];

const CHECK_NAMES: Record<Schemas["CheckAgreementOut"]["check"], string> = {
  grounding: "Grounding",
  answers_question: "Answers the question",
  reference_answer: "Reference answer",
};

const LOW_SAMPLE = "Fewer than 30 sample reviews";

const percent = (rate: number) => `${String(Math.round(rate * 100))}%`;

const plural = (count: number, one: string, many = `${one}s`) => `${String(count)} ${count === 1 ? one : many}`;

/** The 95% interval of a rate that has reviews. */
const interval = (figures: Figures) => `${percent(figures.low ?? 0)} to ${percent(figures.high ?? 0)}`;

/** The agreement rate of figures that have reviews, with the Low sample badge when it rests on fewer than 30. */
function Rate({ figures }: { figures: Figures }) {
  return (
    <span className="inline-flex flex-wrap items-center justify-end gap-2">
      {percent(figures.agreed / figures.reviews)}
      {figures.low_sample && <Badge kind="lowSample" title={LOW_SAMPLE} />}
    </span>
  );
}

/** A table of agreement rows: per check of one Judging setup, or one row per earlier Judging setup. */
function FiguresTable({ caption, first, rows }: { caption: string; first: string; rows: { name: string; figures: Figures }[] }) {
  return (
    <div className={table.wrap}>
      <table className={table.table}>
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            <th scope="col" className={table.th}>
              {first}
            </th>
            {["Reviews", "Agreed", "95% interval", "False passes", "False fails"].map((heading) => (
              <th key={heading} scope="col" className={table.thNumeric}>
                {heading}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(({ name, figures }) => (
            <tr key={name} className={table.row}>
              <th scope="row" className={`${table.td} text-left font-normal`}>
                {name}
              </th>
              <td className={table.tdNumeric}>{figures.reviews}</td>
              <td className={table.tdNumeric}>
                <Rate figures={figures} />
              </td>
              <td className={table.tdNumeric}>{interval(figures)}</td>
              <td className={table.tdNumeric}>{figures.false_passes}</td>
              <td className={table.tdNumeric}>{figures.false_fails}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** The current Judging setup's figures: the rate and its interval, false passes and false fails, then per check. */
function Current({ current }: { current: Agreement }) {
  if (current.reviews === 0) return <p className={text.muted}>No sample reviews under this Judging setup yet.</p>;
  return (
    <div className="flex flex-col gap-3">
      <div
        className={`flex flex-col gap-1 rounded-2xl border px-5 py-4 ${current.low_sample ? "border-dashed border-field bg-canvas" : "border-line bg-surface"}`}
      >
        <div className="flex flex-wrap items-center gap-2">
          <p className={`font-mono text-[22px] ${current.low_sample ? "text-muted" : "text-ink"}`}>{`${percent(current.rate ?? 0)} agreed`}</p>
          {current.low_sample && <Badge kind="lowSample" title={LOW_SAMPLE} />}
        </div>
        <div className="space-y-0.5 text-[13px] text-muted">
          <p>{`95% interval ${interval(current)}`}</p>
          <p>
            {`${String(current.agreed)} of ${plural(current.reviews, "sample review")} agreed: ${plural(current.false_passes, "false pass", "false passes")}, ${plural(current.false_fails, "false fail")}`}
          </p>
        </div>
      </div>
      <FiguresTable
        caption="Agreement per check"
        first="Check"
        rows={current.checks.map((check) => ({ name: CHECK_NAMES[check.check], figures: check }))}
      />
    </div>
  );
}

/**
 * The Evaluation Model agreement card, read by every Member: the current Judging setup's (Evaluation Model and guidance version)
 * agreement with Review sample reviews (rate with its Wilson interval, Low sample under 30, false passes and false fails, overall
 * and per check), how many sample reviews the Organisation and you gave and items were skipped under it, the earlier Judging
 * setups that have reviews, and the way to the Review sample.
 */
export function EvaluationAgreementCard({ organisationId }: { organisationId: string }) {
  const agreement = useEvaluationAgreement(organisationId);
  const headingId = useId();
  if (agreement.isError) return <p role="alert" className={text.muted}>The Evaluation Model agreement could not be loaded. Try again shortly.</p>;
  if (!agreement.data) return null;
  const { current, earlier, reviewed, reviewed_by_you: byYou, skipped } = agreement.data;
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-3 border-t border-line-soft pt-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id={headingId} className={text.subheading}>
          Evaluation Model agreement
        </h3>
        <Link to="/organisations/$organisationId/review-sample" params={{ organisationId }} className={text.link}>
          Review sample
        </Link>
      </div>
      <p className={text.muted}>
        How often Editors, reviewing blind on the Review sample, agree with the Evaluation Model's pass or fail. A false pass is one it
        passed and the Editor failed. Changing the Evaluation Model or the guidance starts a new Judging setup, with new figures.
      </p>
      {current === null ? (
        <p className={text.muted}>No model to judge with yet, so there is no agreement to count.</p>
      ) : (
        <>
          <p className="text-sm text-ink">{judgingSetupLabel(current)}</p>
          <Current current={current} />
          <p className={text.muted}>
            {`${plural(reviewed, "sample review")} in this Organisation, ${String(byYou)} of them yours. ${plural(skipped, "item")} skipped.`}
          </p>
        </>
      )}
      {earlier.length > 0 && (
        <div className="flex flex-col gap-2">
          <h4 className="text-sm font-medium text-ink-2">Earlier Judging setups</h4>
          <FiguresTable
            caption="Earlier Judging setups"
            first="Judging setup"
            rows={earlier.map((setup) => ({ name: judgingSetupLabel(setup), figures: setup }))}
          />
        </div>
      )}
    </section>
  );
}
