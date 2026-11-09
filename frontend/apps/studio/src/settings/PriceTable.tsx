import { type SubmitEvent, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { type Credential, credentialFailure, useCredentials } from "./credentials";
import { formatPrice, type ModelPrices, parsePrice, PRICE_KINDS, type PriceKind, useCredentialPrices, useOverridePrices } from "./prices";

const INPUT = "mt-1 block w-full rounded border border-field bg-surface px-3 py-2 focus:outline-2 focus:outline-accent";
const PRIMARY = "rounded bg-accent px-4 py-2 text-sm font-medium text-on-accent hover:bg-accent-hover disabled:bg-muted";
const SECONDARY = "rounded border border-field px-3 py-1.5 text-sm font-medium hover:bg-sunken";
const INVALID = "Prices are amounts in US dollars per million tokens, like 3 or 0.075, with at most six decimal places.";

function PriceCell({ row, kind }: { row: ModelPrices; kind: PriceKind }) {
  const effective = row.effective[kind];
  if (effective === null) return <span className="text-muted">No price</span>;
  const overridden = row.override?.[kind] != null;
  const platform = row.platform?.[kind];
  return (
    <span>
      {formatPrice(effective)}
      {overridden && (
        <span className="ml-2 inline-block rounded bg-flag-soft px-1.5 text-xs font-medium text-flag">
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
      className="max-w-md space-y-3 rounded border border-field p-4"
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
      <h3 className="font-medium">{`Override prices for ${row.model_name}`}</h3>
      <p className="text-sm text-muted">US dollars per million tokens. Leave a price blank to keep the platform price.</p>
      <FormError message={invalid ? INVALID : credentialFailure(save.error)} />
      {PRICE_KINDS.map(({ kind, name }) => {
        const platform = row.platform?.[kind];
        return (
          <label key={kind} className="block text-sm font-medium">
            {name}
            <input
              className={INPUT}
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
        <button type="submit" className={PRIMARY} disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save prices"}
        </button>
        {row.override && (
          <button
            type="button"
            className={SECONDARY}
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
          className={SECONDARY}
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
  const [saved, setSaved] = useState("");
  if (listed.isError) return <p role="alert">The prices could not be loaded. Try again shortly.</p>;
  if (!listed.data) return <p className="text-sm text-muted">Loading…</p>;
  const rows = listed.data.models;
  const editingRow = rows.find((row) => row.model === editing);
  return (
    <div className="space-y-3">
      {saved && (
        <p role="status" className="text-sm text-accent-ink">
          {saved}
        </p>
      )}
      {rows.length === 0 ? (
        <p className="text-sm text-muted">This credential offers no models.</p>
      ) : (
        <div className="overflow-x-auto">
          <table aria-label={`Prices for ${credential.name}`} className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-field">
                <th scope="col" className="py-2 pr-4">
                  Model
                </th>
                {PRICE_KINDS.map(({ kind, name }) => (
                  <th key={kind} scope="col" className="py-2 pr-4">
                    {name}
                  </th>
                ))}
                {isOwner && (
                  <th scope="col" className="py-2">
                    <span className="sr-only">Actions</span>
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.model} className="border-b border-line">
                  <th scope="row" className="py-2 pr-4 font-medium">
                    {row.model_name}
                  </th>
                  {PRICE_KINDS.map(({ kind }) => (
                    <td key={kind} className="py-2 pr-4">
                      <PriceCell row={row} kind={kind} />
                    </td>
                  ))}
                  {isOwner && (
                    <td className="py-2">
                      <button
                        type="button"
                        className={SECONDARY}
                        aria-label={`Override prices: ${row.model_name}`}
                        onClick={() => {
                          setSaved("");
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
      )}
      {editingRow && (
        <OverrideForm
          key={editingRow.model}
          organisationId={organisationId}
          credentialId={credential.id}
          row={editingRow}
          onDone={(message) => {
            setSaved(message);
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
    <div className="space-y-3">
      <label className="block max-w-md text-sm font-medium">
        Show prices for
        <select
          className={INPUT}
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

/** The price table: each model's price for one credential, with that credential's overrides. */
export function PriceTable({ organisationId, isOwner }: { organisationId: string; isOwner: boolean }) {
  const credentials = useCredentials(organisationId);
  let body;
  if (credentials.isError) body = <p role="alert">The prices could not be loaded. Try again shortly.</p>;
  else if (!credentials.data) body = <p className="text-sm text-muted">Loading…</p>;
  else {
    const [first, ...rest] = [...credentials.data].sort((a, b) => a.name.localeCompare(b.name));
    body =
      first === undefined ? (
        <p className="text-sm text-muted">No credentials yet, so there is nothing to price.</p>
      ) : (
        <CredentialChoice organisationId={organisationId} credentials={[first, ...rest]} isOwner={isOwner} />
      );
  }
  return (
    <section aria-labelledby="prices-heading" className="space-y-4">
      <div className="space-y-1">
        <h2 id="prices-heading" className="text-lg font-semibold">
          Prices
        </h2>
        <p className="text-sm text-muted">
          What each model costs, in US dollars per million tokens. Cost reporting uses the platform price table unless an Owner
          overrides a price for one credential, for example a negotiated rate.
          {isOwner ? "" : " Only Owners can override prices."}
        </p>
      </div>
      {body}
    </section>
  );
}
