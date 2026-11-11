import { useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { button, field, Notice, surface, text } from "../design";
import {
  MAX_RETENTION_DAYS,
  MIN_RETENTION_DAYS,
  RetentionRequestError,
  useOrganisationDetails,
  useSetRetentionWindow,
} from "./retention";

const RANGE = `Choose from ${String(MIN_RETENTION_DAYS)} to ${String(MAX_RETENTION_DAYS)} days.`;

function failure(error: Error | null): string | undefined {
  if (error === null) return undefined;
  if (error instanceof RetentionRequestError && error.status === 422) return RANGE;
  return "The Retention Window could not be saved. Try again shortly.";
}

function RetentionForm({ organisationId, days }: { organisationId: string; days: number }) {
  const save = useSetRetentionWindow(organisationId);
  const [value, setValue] = useState(String(days));
  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate(Number(value));
      }}
    >
      <FormError message={failure(save.error)} />
      <label htmlFor="retention-days" className={field.label}>
        Retention Window (days)
      </label>
      <div className="flex items-center gap-2">
        <input
          id="retention-days"
          type="number"
          className={`${field.inputMono} mt-0 w-28`}
          min={MIN_RETENTION_DAYS}
          max={MAX_RETENTION_DAYS}
          required
          aria-describedby="retention-range"
          value={value}
          onChange={(event) => {
            save.reset();
            setValue(event.currentTarget.value);
          }}
        />
        <button type="submit" className={button.primary} disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save"}
        </button>
      </div>
      <p id="retention-range" className={text.small}>
        {RANGE} Changes are recorded in the Audit log.
      </p>
      {save.isSuccess && <Notice tone="success">Saved.</Notice>}
    </form>
  );
}

/**
 * The Retention Window: how long Message text and feedback comments are kept before the daily
 * purge clears them. Owners change it; everyone else sees it.
 */
export function RetentionWindow({ organisationId, isOwner }: { organisationId: string; isOwner: boolean }) {
  const organisation = useOrganisationDetails(organisationId);
  let body;
  if (organisation.isError) {
    body = <p role="alert" className={text.muted}>The Retention Window could not be loaded. Try again shortly.</p>;
  } else if (organisation.data === undefined) {
    body = <p role="status" className={text.muted}>Loading the Retention Window…</p>;
  } else {
    const days = organisation.data.retention_days;
    body = (
      <>
        <p className={text.muted}>
          {`Message text and feedback comments are kept for ${String(days)} days, then purged every night. Metrics are kept.`}
        </p>
        {isOwner ? (
          <RetentionForm organisationId={organisationId} days={days} />
        ) : (
          <p className={text.muted}>Only Owners can change this.</p>
        )}
      </>
    );
  }
  return (
    <section aria-labelledby="retention-heading" className={`${surface.panel} flex flex-col gap-3`}>
      <h2 id="retention-heading" className={text.heading}>
        Retention
      </h2>
      {body}
    </section>
  );
}
