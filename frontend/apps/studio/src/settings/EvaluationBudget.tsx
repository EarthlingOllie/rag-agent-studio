import { type SubmitEvent, useId, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { button, field, Meter, Skeleton, text, useToast } from "../design";
import { dollars } from "../projects/format";
import { credentialFailure } from "./credentials";
import { type EvaluationBudget, useEvaluationBudget, useSetEvaluationBudget } from "./evaluationSettings";

const resetDay = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });

function BudgetMeter({ found }: { found: EvaluationBudget & { evaluation_budget_usd: string } }) {
  const budget = Number(found.evaluation_budget_usd);
  const spent = Number(found.spent_usd);
  return (
    <div className="flex flex-col gap-1">
      <Meter
        label="Evaluation budget spent this month"
        value={spent}
        max={budget}
        format={(amount) => dollars(String(amount))}
      />
      <p className={text.muted}>
        {found.exhausted
          ? `Spent: no Visitor replies are judged until the budget is raised or the month ends on ${resetDay.format(new Date(found.resets_at))} (UTC). `
          : ""}
        Judgements already under way when the budget is reached still finish, so the spend can pass it slightly.
      </p>
    </div>
  );
}

/** This month's spend on Live Verdicts against the Evaluation budget, or that there is none and nothing is judged. */
export function EvaluationBudgetMeter({ organisationId }: { organisationId: string }) {
  const found = useEvaluationBudget(organisationId);
  if (found.isError) return <p role="alert" className={text.muted}>The Evaluation budget could not be loaded. Try again shortly.</p>;
  if (found.isPending) return <Skeleton label="Loading the Evaluation budget" />;
  const { evaluation_budget_usd: budget } = found.data;
  if (budget === null) return <p className={text.muted}>No Evaluation budget is set, so no Visitor replies are judged.</p>;
  return <BudgetMeter found={{ ...found.data, evaluation_budget_usd: budget }} />;
}

function BudgetForm({ organisationId, current }: { organisationId: string; current: string | null }) {
  const save = useSetEvaluationBudget(organisationId);
  const toast = useToast();
  const hintId = useId();
  const inputId = useId();
  const [edited, setEdited] = useState<string | null>(null);
  const amount = edited ?? current ?? "";

  function change(budget: string | null) {
    save.mutate(budget, {
      onSuccess: (next) => {
        setEdited(null);
        toast.show(
          next.evaluation_budget_usd === null
            ? "The Evaluation budget is removed: no Visitor replies are judged."
            : `The Evaluation budget is now ${dollars(next.evaluation_budget_usd)} a month.`,
        );
      },
    });
  }

  return (
    <form
      aria-label="Set the Evaluation budget"
      className="flex flex-col gap-3"
      onSubmit={(event: SubmitEvent<HTMLFormElement>) => {
        event.preventDefault();
        change(amount);
      }}
    >
      <div className="flex flex-col gap-1">
        <label htmlFor={inputId} className={field.label}>
          Evaluation budget (US dollars a month)
        </label>
        <input
          id={inputId}
          type="number"
          min={0.01}
          step={0.01}
          required
          aria-describedby={hintId}
          className={`${field.inputMono} max-w-48`}
          value={amount}
          onChange={(event) => {
            save.reset();
            setEdited(event.target.value);
          }}
        />
        <p id={hintId} className={field.hint}>
          The most Live Verdicts may spend each calendar month (UTC). Once it is spent, sampling pauses across the Organisation
          until the 1st and every Owner is emailed once. Evaluation Runs are never capped.
        </p>
      </div>
      <FormError message={credentialFailure(save.error)} />
      <div className="flex flex-wrap items-center gap-3">
        <button type="submit" className={button.primary} disabled={save.isPending || amount === ""}>
          {save.isPending ? "Saving…" : "Save Evaluation budget"}
        </button>
        {current !== null && (
          <button
            type="button"
            className={button.secondary}
            disabled={save.isPending}
            onClick={() => {
              change(null);
            }}
          >
            Remove Evaluation budget
          </button>
        )}
      </div>
    </form>
  );
}

/** The Evaluation budget in Organisation settings (Models): this month's meter for every Member, the field for Owners. */
export function EvaluationBudgetSettings({ organisationId, isOwner }: { organisationId: string; isOwner: boolean }) {
  const found = useEvaluationBudget(organisationId);
  return (
    <div className="flex flex-col gap-3 border-t border-line pt-4">
      <h3 className={text.subheading}>Evaluation budget</h3>
      {found.data && (
        <p className="text-sm text-ink">
          {found.data.evaluation_budget_usd === null
            ? "Evaluation budget: none"
            : `Evaluation budget: ${dollars(found.data.evaluation_budget_usd)} a month`}
        </p>
      )}
      <EvaluationBudgetMeter organisationId={organisationId} />
      {isOwner ? (
        found.data && <BudgetForm organisationId={organisationId} current={found.data.evaluation_budget_usd} />
      ) : (
        <p className={text.muted}>Only Owners can change the Evaluation budget.</p>
      )}
    </div>
  );
}
