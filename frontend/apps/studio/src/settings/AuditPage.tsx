import { useState } from "react";

import { type AuditEventPage, type AuditFilters, NO_FILTERS, PAGE_SIZE, useAuditEvents, useAuditFacets } from "./audit";

type AuditEvent = AuditEventPage["items"][number];

const INPUT = "rounded border border-slate-400 bg-white px-2 py-1 text-sm";

/** `2026-06-01T09:30:00Z` → `2026-06-01 09:30 UTC`, the same for every viewer. */
function formatTime(iso: string): string {
  return `${new Date(iso).toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

function formatValues(values: AuditEvent["before"]): string {
  return values ? JSON.stringify(values) : "—";
}

function EventRow({ event }: { event: AuditEvent }) {
  return (
    <tr className="border-t border-slate-200 align-top">
      <td className="whitespace-nowrap py-2 pr-4">{formatTime(event.occurred_at)}</td>
      <td className="py-2 pr-4">{event.actor?.name ?? "System"}</td>
      <td className="py-2 pr-4 font-mono text-xs">{event.action}</td>
      <td className="py-2 pr-4">{event.target.id ? `${event.target.type} ${event.target.id}` : event.target.type}</td>
      <td className="break-all py-2 pr-4 font-mono text-xs">{formatValues(event.before)}</td>
      <td className="break-all py-2 font-mono text-xs">{formatValues(event.after)}</td>
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
    <fieldset className="mt-6 flex flex-wrap items-end gap-4">
      <legend className="sr-only">Filter Audit Events</legend>
      <label className="flex flex-col gap-1 text-sm">
        Actor
        <select className={INPUT} value={filters.actorId} onChange={set("actorId")}>
          <option value="">Anyone</option>
          {facets.data?.actors.map((actor) => (
            <option key={actor.id} value={actor.id}>
              {actor.name}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Action
        <select className={INPUT} value={filters.action} onChange={set("action")}>
          <option value="">Any action</option>
          {facets.data?.actions.map((action) => (
            <option key={action} value={action}>
              {action}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm">
        From (UTC)
        <input type="date" className={INPUT} value={filters.from} onChange={set("from")} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        To (UTC)
        <input type="date" className={INPUT} value={filters.to} onChange={set("to")} />
      </label>
    </fieldset>
  );
}

function Results({ data }: { data: AuditEventPage }) {
  if (data.items.length === 0) return <p className="mt-6 text-slate-700">No Audit Events match these filters.</p>;
  return (
    <div className="mt-6 overflow-x-auto">
      <table className="w-full text-left text-sm" aria-label="Audit Events">
        <thead>
          <tr className="text-slate-700">
            <th scope="col" className="py-2 pr-4 font-medium">When</th>
            <th scope="col" className="py-2 pr-4 font-medium">Actor</th>
            <th scope="col" className="py-2 pr-4 font-medium">Action</th>
            <th scope="col" className="py-2 pr-4 font-medium">Target</th>
            <th scope="col" className="py-2 pr-4 font-medium">Before</th>
            <th scope="col" className="py-2 font-medium">After</th>
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

function Pager({ data, onPage }: { data: AuditEventPage; onPage: (page: number) => void }) {
  if (data.total === 0) return null;
  const pages = Math.ceil(data.total / PAGE_SIZE);
  const BUTTON = "rounded border border-slate-400 px-3 py-1 text-sm hover:bg-slate-100 disabled:opacity-50";
  return (
    <div className="mt-4 flex items-center gap-4">
      <button type="button" className={BUTTON} disabled={data.page <= 1} onClick={() => { onPage(data.page - 1); }}>
        Previous page
      </button>
      <p className="text-sm text-slate-700">
        Page {data.page} of {pages} · {data.total} {data.total === 1 ? "event" : "events"}
      </p>
      <button type="button" className={BUTTON} disabled={data.page >= pages} onClick={() => { onPage(data.page + 1); }}>
        Next page
      </button>
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
        <p role="status" className="mt-6 text-slate-700">
          Loading Audit Events…
        </p>
      )}
      {events.isError && (
        <p role="alert" className="mt-6 text-red-800">
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

/** The Audit tab: Owners browse and filter the Organisation's Audit Events. */
export function AuditPage({ organisationId, isOwner }: { organisationId: string; isOwner: boolean }) {
  return (
    <section aria-labelledby="audit-heading">
      <h2 id="audit-heading" className="text-xl font-semibold">
        Audit
      </h2>
      {isOwner ? (
        <>
          <p className="mt-2 text-slate-700">Every security and configuration change in this Organisation, newest first.</p>
          <AuditLog organisationId={organisationId} />
        </>
      ) : (
        <p className="mt-2 text-slate-700">Only Owners can view Audit Events.</p>
      )}
    </section>
  );
}
