import { type SubmitEvent, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { button, field, surface, text, useToast } from "../design";
import { type Credential, credentialFailure, useCredentials } from "./credentials";
import { formatPrice, parsePrice, useCredentialPrices, useOverrideVoicePrice, type VoicePrice } from "./prices";

const INVALID = "A per-minute price is an amount in US dollars, like 0.1 or 0.075, with at most six decimal places.";

function VoicePriceForm({ organisationId, credential, voice }: { organisationId: string; credential: Credential; voice: VoicePrice }) {
  const save = useOverrideVoicePrice(organisationId, credential.id);
  const toast = useToast();
  const [typed, setTyped] = useState(voice.override ?? "");
  const [invalid, setInvalid] = useState(false);
  const send = (perMinute: string | null, message: string) => {
    save.mutate(perMinute, {
      onSuccess: (saved) => {
        setTyped(saved.override ?? "");
        toast.show(message);
      },
    });
  };
  return (
    <form
      aria-label={`Override the per-minute price for ${credential.name}`}
      className="flex flex-col gap-3"
      onSubmit={(event: SubmitEvent<HTMLFormElement>) => {
        event.preventDefault();
        const parsed = parsePrice(typed);
        if (parsed === undefined || parsed === null) {
          setInvalid(true);
          return;
        }
        setInvalid(false);
        send(parsed, `The per-minute price for ${credential.name} was saved.`);
      }}
    >
      <FormError message={invalid ? INVALID : credentialFailure(save.error)} />
      <label className={field.label}>
        Per-minute price (US dollars)
        <input
          className={field.inputMono}
          inputMode="decimal"
          value={typed}
          placeholder={voice.platform === null ? "No platform price" : `Platform: ${formatPrice(voice.platform)}`}
          onChange={(event) => {
            setTyped(event.target.value);
          }}
        />
      </label>
      <div className="flex flex-wrap gap-2">
        <button type="submit" className={button.primary} disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save price"}
        </button>
        {voice.override !== null && (
          <button
            type="button"
            className={button.secondary}
            disabled={save.isPending}
            onClick={() => {
              setInvalid(false);
              send(null, `${credential.name} uses the platform per-minute price again.`);
            }}
          >
            Use platform price
          </button>
        )}
      </div>
    </form>
  );
}

/**
 * A voice credential's price per Call minute, which each Call's Voice Cost is worked out from
 * when it ends: the platform's, or an Owner's override to match their voice plan.
 */
export function VoicePriceCard({ organisationId, credential, isOwner }: { organisationId: string; credential: Credential; isOwner: boolean }) {
  const listed = useCredentialPrices(organisationId, credential.id);
  let body;
  if (listed.isError) body = <p role="alert" className={text.muted}>The per-minute price could not be loaded. Try again shortly.</p>;
  else if (!listed.data?.voice) body = <p className={text.muted}>Loading…</p>;
  else {
    const voice = listed.data.voice;
    body = (
      <>
        <p className="flex flex-wrap items-center gap-2 text-sm text-ink">
          {voice.effective === null ? "No per-minute price" : `${formatPrice(voice.effective)} per Call minute`}
          {voice.override !== null && (
            <span className="inline-block rounded-full bg-flag-soft px-2 py-0.5 text-xs font-medium text-flag">
              {voice.platform === null ? "Override" : `Override (platform ${formatPrice(voice.platform)})`}
            </span>
          )}
        </p>
        <p className={text.muted}>
          {voice.effective === null
            ? "Calls with this credential have no known Voice Cost until a price is set."
            : "Each Call's Voice Cost is its minutes times the price in effect when it ends."}
        </p>
        {isOwner && <VoicePriceForm key={voice.override ?? ""} organisationId={organisationId} credential={credential} voice={voice} />}
      </>
    );
  }
  return (
    <section aria-label={`Per-minute price for ${credential.name}`} className={`${surface.panel} flex max-w-md flex-col gap-3`}>
      <h3 className={text.subheading}>{`Per-minute price for ${credential.name}`}</h3>
      {body}
    </section>
  );
}

/** The Credentials page's voice prices: one card per credential that carries Calls; nothing without one. */
export function VoicePrices({ organisationId, isOwner }: { organisationId: string; isOwner: boolean }) {
  const credentials = useCredentials(organisationId);
  const voiced = (credentials.data ?? []).filter((credential) => credential.capabilities.includes("voice"));
  if (voiced.length === 0) return null;
  return (
    <section aria-labelledby="voice-prices-heading" className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <h3 id="voice-prices-heading" className={text.subheading}>
          Voice prices
        </h3>
        <p className={text.muted}>
          Calls are priced per minute, apart from the Cost of their replies.
          {isOwner ? " Override a credential's price to match your ElevenLabs plan." : " Only Owners can override prices."}
        </p>
      </div>
      {voiced.map((credential) => (
        <VoicePriceCard key={credential.id} organisationId={organisationId} credential={credential} isOwner={isOwner} />
      ))}
    </section>
  );
}
