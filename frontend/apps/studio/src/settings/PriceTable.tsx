import { type SubmitEvent, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { button, field, Pagination, surface, table, text, useToast } from "../design";
import { type Credential, credentialFailure, useCredentials } from "./credentials";
import { formatPrice, type ModelPrices, parsePrice, PRICE_KINDS, type PriceKind, useCredentialPrices, useOverridePrices } from "./prices";

const INVALID = "Prices are amounts in US dollars per million tokens, like 3 or 0.075, with at most six decimal places.";
/** Models per page of the price table. */
export const PRICES_PAGE_SIZE = 10;

function PriceCell({ row, kind }: { row: ModelPrices; kind: PriceKind }) {
  const effective = row.effective[kind];
  if (effective === null) return <span className="font-sans text-sm text-muted">No price</span>;
  const overridden = row.override?.[kind] != null;
  const platform = row.platform?.[kind];
  return (
    <span>
      {formatPrice(effective)}
      {overridden && (
        <span className="ml-2 inline-block rounded-full bg-flag-soft px-2 py-0.5 font-sans text-xs font-medium text-flag">
          {platform === undefined ? "Override" : `Override (platform ${formatPrice(platform)})`}
        </span>
      )}
    </span>
  );
}

function OverrideForm({
  organisationId,
  credentialId,
  row,
  onDone,
}: {
  organisationId: string;
  credentialId: string;
  row: ModelPrices;
  onDone: (message: string) => void;
}) {
  const save = useOverridePrices(organisationId, credentialId);
  const [typed, setTyped] = useState<Record<PriceKind, string>>({
    input: row.override?.input ?? "",
    output: row.override?.output ?? "",
    cached_input: row.override?.cached_input ?? "",
  });
  const [invalid, setInvalid] = useState(false);
  const send = (prices: Record<PriceKind, string | null>, message: string) => {
    save.mutate({ model: row.model, ...prices }, { onSuccess: () => { onDone(message); } });
  };
  return (
    <form
      aria-label={`Override prices for ${row.model_name}`}
      className={`${surface.panel} flex max-w-md flex-col gap-3`}
      onSubmit={(event: SubmitEvent<HTMLFormElement>) => {
        event.preventDefault();
        const parsed = { input: parsePrice(typed.input), output: parsePrice(typed.output), cached_input: parsePrice(typed.cached_input) };
        const { input, output, cached_input: cachedInput } = parsed;
        if (input === undefined || output === undefined || cachedInput === undefined) {
          setInvalid(true);
          return;
        }
        setInvalid(false);
        send({ input, output, cached_input: cachedInput }, `Prices for ${row.model_name} saved.`);
      }}
    >
      <h3 className={text.subheading}>{`Override prices for ${row.model_name}`}</h3>
      <p className={text.muted}>US dollars per million tokens. Leave a price blank to keep the platform price.</p>
      <FormError message={invalid ? INVALID : credentialFailure(save.error)} />
      {PRICE_KINDS.map(({ kind, name }) => {
        const platform = row.platform?.[kind];
        return (
          <label key={kind} className={field.label}>
            {name}
            <input
              className={field.inputMono}
              inputMode="decimal"
              value={typed[kind]}
              placeholder={platform === undefined ? "No platform price" : `Platform: ${formatPrice(platform)}`}
              onChange={(event) => {
                setTyped({ ...typed, [kind]: event.target.value });
              }}
            />
          </label>
        );
      })}
      <div className="flex flex-wrap gap-2">
        <button type="submit" className={button.primary} disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save prices"}
        </button>
        {row.override && (
          <button
            type="button"
            className={button.secondary}
            disabled={save.isPending}
            onClick={() => {
              setInvalid(false);
              send({ input: null, output: null, cached_input: null }, `${row.model_name} uses the platform prices again.`);
            }}
          >
            Use platform prices
          </button>
        )}
        <button
          type="button"
          className={button.secondary}
          onClick={() => {
            onDone("");
          }}
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

function CredentialPriceTable({ organisationId, credential, isOwner }: { organisationId: string; credential: Credential; isOwner: boolean }) {
  const listed = useCredentialPrices(organisationId, credential.id);
  const [editing, setEditing] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const toast = useToast();
  if (listed.isError) return <p role="alert" className={text.muted}>The prices could not be loaded. Try again shortly.</p>;
  if (!listed.data) return <p className={text.muted}>Loading…</p>;
  const rows = listed.data.models;
  const editingRow = rows.find((row) => row.model === editing);
  const pageCount = Math.ceil(rows.length / PRICES_PAGE_SIZE);
  const shown = rows.slice((page - 1) * PRICES_PAGE_SIZE, page * PRICES_PAGE_SIZE);
  return (
    <div className="flex flex-col gap-4">
      {rows.length === 0 ? (
        <p className={text.muted}>This credential offers no models.</p>
      ) : (
        <>
          <div className={table.wrap}>
            <table aria-label={`Prices for ${credential.name}`} className={`${table.table} min-w-[640px]`}>
              <thead>
                <tr>
                  <th scope="col" className={table.th}>
                    Model
                  </th>
                  {PRICE_KINDS.map(({ kind, name }) => (
                    <th key={kind} scope="col" className={table.th}>
                      {name}
                    </th>
                  ))}
                  {isOwner && (
                    <th scope="col" className={table.th}>
                      <span className="sr-only">Actions</span>
                    </th>
                  )}
                </tr>
              </thead>
              <tbody>
                {shown.map((row) => (
                  <tr key={row.model} className={table.row}>
                    <th scope="row" className={`${table.td} text-left font-medium`}>
                      {row.model_name}
                    </th>
                    {PRICE_KINDS.map(({ kind }) => (
                      <td key={kind} className={`${table.td} font-mono text-[13px]`}>
                        <PriceCell row={row} kind={kind} />
                      </td>
                    ))}
                    {isOwner && (
                      <td className={`${table.td} text-right`}>
                        <button
                          type="button"
                          className={button.secondary}
                          aria-label={`Override prices: ${row.model_name}`}
                          onClick={() => {
                            setEditing(row.model);
                          }}
                        >
                          Override
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination label={`Prices for ${credential.name} pages`} page={page} pageCount={pageCount} onPageChange={setPage} />
        </>
      )}
      {editingRow && (
        <OverrideForm
          key={editingRow.model}
          organisationId={organisationId}
          credentialId={credential.id}
          row={editingRow}
          onDone={(message) => {
            if (message) toast.show(message);
            setEditing(null);
          }}
        />
      )}
    </div>
  );
}

function CredentialChoice({ organisationId, credentials, isOwner }: { organisationId: string; credentials: [Credential, ...Credential[]]; isOwner: boolean }) {
  // Until an Owner chooses, and if the chosen credential goes away, the first is shown.
  const [chosenId, setChosenId] = useState<string | null>(null);
  const chosen = credentials.find((credential) => credential.id === chosenId) ?? credentials[0];
  return (
    <div className="flex flex-col gap-4">
      <label className={`${field.label} max-w-md`}>
        Show prices for
        <select
          className={field.select}
          value={chosen.id}
          onChange={(event) => {
            setChosenId(event.target.value);
          }}
        >
          {credentials.map((credential) => (
            <option key={credential.id} value={credential.id}>
              {credential.name}
            </option>
          ))}
        </select>
      </label>
      <CredentialPriceTable key={chosen.id} organisationId={organisationId} credential={chosen} isOwner={isOwner} />
    </div>
  );
}

/**
 * The price table: each model's price for one credential, with that credential's overrides, ten
 * models to a page. A saved override is confirmed by a toast.
 */
export function PriceTable({ organisationId, isOwner }: { organisationId: string; isOwner: boolean }) {
  const credentials = useCredentials(organisationId);
  let body;
  if (credentials.isError) body = <p role="alert" className={text.muted}>The prices could not be loaded. Try again shortly.</p>;
  else if (!credentials.data) body = <p className={text.muted}>Loading…</p>;
  else {
    const [first, ...rest] = [...credentials.data].sort((a, b) => a.name.localeCompare(b.name));
    body =
      first === undefined ? (
        <p className={text.muted}>No credentials yet, so there is nothing to price.</p>
      ) : (
        <CredentialChoice organisationId={organisationId} credentials={[first, ...rest]} isOwner={isOwner} />
      );
  }
  return (
    <section aria-labelledby="prices-heading" className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2 id="prices-heading" className={text.heading}>
          Prices
        </h2>
        <p className={text.muted}>
          What each model costs, in US dollars per million tokens. Cost reporting uses the platform price table unless an Owner
          overrides a price for one credential, for example a negotiated rate.
          {isOwner ? "" : " Only Owners can override prices."}
        </p>
      </div>
      {body}
    </section>
  );
}
