import { useState } from "react";

import { field, Pagination, table, text } from "../design";
import { type AuditEventPage, type AuditFilters, NO_FILTERS, PAGE_SIZE, useAuditEvents, useAuditFacets } from "./audit";

type AuditEvent = AuditEventPage["items"][number];

const FILTER = "block h-10 min-w-40 rounded-xl border border-field bg-surface px-3 text-sm font-normal text-ink";

/** `2026-06-01T09:30:00Z` → `2026-06-01 09:30 UTC`, the same for every viewer. */
export function formatTime(iso: string): string {
  return `${new Date(iso).toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

function formatValues(values: AuditEvent["before"]): string {
  return values ? JSON.stringify(values) : "—";
}

function EventRow({ event }: { event: AuditEvent }) {
  return (
    <tr className={`${table.row} align-top`}>
      <td className={`${table.tdMuted} font-mono text-[13px] whitespace-nowrap`}>{formatTime(event.occurred_at)}</td>
      <td className={table.td}>{event.actor?.name ?? "System"}</td>
      <td className={`${table.td} font-mono text-xs`}>{event.action}</td>
      <td className={`${table.td} break-all`}>{event.target.id ? `${event.target.type} ${event.target.id}` : event.target.type}</td>
      <td className={`${table.tdMuted} font-mono text-xs break-all`}>{formatValues(event.before)}</td>
      <td className={`${table.tdMuted} font-mono text-xs break-all`}>{formatValues(event.after)}</td>
    </tr>
  );
}

function Filters({
  organisationId,
  filters,
  onChange,
}: {
  organisationId: string;
  filters: AuditFilters;
  onChange: (filters: AuditFilters) => void;
}) {
  const facets = useAuditFacets(organisationId);
  const set = (key: keyof AuditFilters) => (event: { currentTarget: { value: string } }) => {
    onChange({ ...filters, [key]: event.currentTarget.value });
  };
  return (
    <fieldset className="flex flex-wrap items-end gap-3">
      <legend className="sr-only">Filter Audit Events</legend>
      <label className={`${field.label} flex flex-col gap-1.5`}>
        Actor
        <select className={FILTER} value={filters.actorId} onChange={set("actorId")}>
          <option value="">Anyone</option>
          {facets.data?.actors.map((actor) => (
            <option key={actor.id} value={actor.id}>
              {actor.name}
            </option>
          ))}
        </select>
      </label>
      <label className={`${field.label} flex flex-col gap-1.5`}>
        Action
        <select className={FILTER} value={filters.action} onChange={set("action")}>
          <option value="">Any action</option>
          {facets.data?.actions.map((action) => (
            <option key={action} value={action}>
              {action}
            </option>
          ))}
        </select>
      </label>
      <label className={`${field.label} flex flex-col gap-1.5`}>
        From (UTC)
        <input type="date" className={FILTER} value={filters.from} onChange={set("from")} />
      </label>
      <label className={`${field.label} flex flex-col gap-1.5`}>
        To (UTC)
        <input type="date" className={FILTER} value={filters.to} onChange={set("to")} />
      </label>
    </fieldset>
  );
}

function Results({ data }: { data: AuditEventPage }) {
  if (data.items.length === 0) return <p className={text.muted}>No Audit Events match these filters.</p>;
  return (
    <div className={table.wrap}>
      <table className={`${table.table} min-w-[880px]`} aria-label="Audit Events">
        <thead>
          <tr>
            <th scope="col" className={table.th}>When</th>
            <th scope="col" className={table.th}>Actor</th>
            <th scope="col" className={table.th}>Action</th>
            <th scope="col" className={table.th}>Target</th>
            <th scope="col" className={table.th}>Before</th>
            <th scope="col" className={table.th}>After</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((event) => (
            <EventRow key={event.id} event={event} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Where the Owner is in the history, then the pages (shown when there is more than one). */
function Pager({ data, onPage }: { data: AuditEventPage; onPage: (page: number) => void }) {
  if (data.total === 0) return null;
  const pages = Math.ceil(data.total / PAGE_SIZE);
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p className={text.muted}>
        Page {data.page} of {pages} · {data.total} {data.total === 1 ? "event" : "events"}
      </p>
      <Pagination label="Audit Events pages" page={data.page} pageCount={pages} onPageChange={onPage} />
    </div>
  );
}

function AuditLog({ organisationId }: { organisationId: string }) {
  const [filters, setFilters] = useState<AuditFilters>(NO_FILTERS);
  const [page, setPage] = useState(1);
  const events = useAuditEvents(organisationId, filters, page);

  return (
    <>
      <Filters
        organisationId={organisationId}
        filters={filters}
        onChange={(next) => {
          setFilters(next);
          setPage(1);
        }}
      />
      {events.isPending && (
        <p role="status" className={text.muted}>
          Loading Audit Events…
        </p>
      )}
      {events.isError && (
        <p role="alert" className="text-sm text-danger">
          Audit Events could not be loaded. Try again shortly.
        </p>
      )}
      {events.data && (
        <>
          <Results data={events.data} />
          <Pager data={events.data} onPage={setPage} />
        </>
      )}
    </>
  );
}

/** Audit settings: Owners browse and filter the Organisation's Audit Events. */
export function AuditPage({ organisationId, isOwner }: { organisationId: string; isOwner: boolean }) {
  return (
    <section aria-labelledby="audit-heading" className="flex flex-col gap-5">
      <h2 id="audit-heading" className={text.heading}>
        Audit
      </h2>
      {isOwner ? (
        <>
          <p className={`${text.muted} -mt-3`}>Every security and configuration change in this Organisation, newest first.</p>
          <AuditLog organisationId={organisationId} />
        </>
      ) : (
        <p className={`${text.muted} -mt-3`}>Only Owners can view Audit Events.</p>
      )}
    </section>
  );
}
