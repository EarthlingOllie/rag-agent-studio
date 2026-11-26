import { Link } from "@tanstack/react-router";
import { type SubmitEvent, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { button, CodeBlock, EditableList, field, Meter, Notice, Skeleton, surface, text as type } from "../design";
import { useCredentials } from "../settings/credentials";
import { useEvaluationBudget } from "../settings/evaluationSettings";
import type { Agent } from "./agents";
import {
  embedSnippet,
  type OperationalSettings,
  type SnippetLayout,
  useChangeOperationalSettings,
  useOperationalSettings,
  useCallMinutes,
  useTokenUsage,
  useVoices,
} from "./embed";

const CARD = `${surface.panel} flex flex-col gap-4`;

/** The Embed Snippet for the chosen Launcher, to copy into the pages that show the Agent. */
function Snippet({ agent }: { agent: Agent }) {
  const [launcher, setLauncher] = useState<SnippetLayout["launcher"]>("theme");
  const [target, setTarget] = useState("#chat");
  const layout: SnippetLayout = launcher === "inline" ? { launcher, target } : { launcher };
  const snippet = embedSnippet(agent.public_id, window.location.origin, layout);

  return (
    <>
      <p className={type.muted}>Paste this into the pages where Visitors should chat with the Agent&apos;s Live Version.</p>
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-48">
          <label htmlFor="snippet-launcher" className={field.label}>
            Launcher
          </label>
          <select
            id="snippet-launcher"
            value={launcher}
            onChange={(event) => {
              setLauncher(event.target.value as SnippetLayout["launcher"]);
            }}
            className={field.select}
          >
            <option value="theme">The Theme&apos;s Launcher</option>
            <option value="bubble">Bubble in the corner</option>
            <option value="inline">Inline in a container</option>
          </select>
        </div>
        {launcher === "inline" && (
          <div className="min-w-48">
            <label htmlFor="snippet-target" className={field.label}>
              Container selector
            </label>
            <input
              id="snippet-target"
              value={target}
              onChange={(event) => {
                setTarget(event.target.value);
              }}
              spellCheck={false}
              className={field.inputMono}
            />
          </div>
        )}
      </div>
      <CodeBlock label="Embed Snippet" code={snippet} />
    </>
  );
}

type SettingsPath = { organisation_id: string; project_id: string; agent_id: string };

/** The sites allowed to show the Agent, edited as a list and saved together. */
function AllowedOrigins({ path }: { path: SettingsPath }) {
  const settings = useOperationalSettings(path);
  const save = useChangeOperationalSettings(path);
  const [edited, setEdited] = useState<string[] | null>(null);
  // Until the saved list is here, saving would replace it with whatever the list holds.
  const loaded = settings.isSuccess;

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    save.mutate(
      // The button is enabled only once the saved list is loaded.
      { allowed_origins: edited ?? (settings.data as OperationalSettings).allowed_origins },
      {
        onSuccess: () => {
          setEdited(null);
        },
      },
    );
  }

  let list;
  if (settings.isError) list = <p className={type.muted}>The Operational Settings could not be loaded.</p>;
  else if (!loaded) list = <Skeleton label="Loading the Allowed Origins" lines={2} />;
  else
    list = (
      <EditableList
        label="Allowed Origins"
        inputLabel="Add an Allowed Origin"
        placeholder="https://www.example.com"
        items={edited ?? settings.data.allowed_origins}
        onChange={(items) => {
          save.reset();
          setEdited(items);
        }}
        emptyWarning="No site can embed this Agent until you add an origin."
      />
    );

  return (
    <section aria-label="Allowed Origins" className={CARD}>
      <form onSubmit={onSubmit} className="flex flex-col gap-3">
        {list}
        <p className={field.hint}>
          A site such as https://www.example.com, https://*.example.com for all its subdomains, or http://localhost:3000
          (http://localhost:* for any port) while developing. Only pages on these sites can show the Agent.
        </p>
        <FormError message={save.error?.message} />
        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" className={button.secondary} disabled={!loaded || save.isPending}>
            Save Allowed Origins
          </button>
          <p role="status" className={type.muted}>
            {save.isSuccess ? "Saved. Pages on these sites can show the Agent now." : ""}
          </p>
        </div>
      </form>
    </section>
  );
}

const UNAVAILABLE_TEXT_MAX = 500;

function UnavailableText({ path }: { path: SettingsPath }) {
  const settings = useOperationalSettings(path);
  const save = useChangeOperationalSettings(path);
  const [edited, setEdited] = useState<string | null>(null);
  const text = edited ?? settings.data?.unavailable_text ?? "";
  const loaded = settings.isSuccess;

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    save.mutate(
      { unavailable_text: text },
      {
        onSuccess: () => {
          setEdited(null);
        },
      },
    );
  }

  return (
    <section className={CARD}>
    <form onSubmit={onSubmit} className="flex flex-col gap-3">
      <label htmlFor="unavailable-text" className={type.subheading}>
        Unavailable text
      </label>
      <p id="unavailable-text-hint" className={type.muted}>
        What Visitors see when the Agent can&apos;t answer. Leave it empty for the default.
      </p>
      <textarea
        id="unavailable-text"
        aria-describedby="unavailable-text-hint"
        rows={2}
        maxLength={UNAVAILABLE_TEXT_MAX}
        className={field.textarea}
        disabled={!loaded}
        value={text}
        onChange={(event) => {
          save.reset();
          setEdited(event.target.value);
        }}
      />
      <FormError message={save.error?.message} />
      <div className="flex items-center gap-3">
        <button type="submit" className={button.secondary} disabled={!loaded || save.isPending}>
          Save unavailable text
        </button>
        <p role="status" className={type.muted}>
          {save.isSuccess ? "Saved. Visitors see it from their next message." : ""}
        </p>
      </div>
    </form>
    </section>
  );
}

type Limits = { conversation: string; ip: string };

function RateLimits({ path }: { path: SettingsPath }) {
  const settings = useOperationalSettings(path);
  const save = useChangeOperationalSettings(path);
  const [edited, setEdited] = useState<Limits | null>(null);
  const loaded = settings.isSuccess;
  const limits: Limits = edited ?? {
    conversation: String(settings.data?.conversation_messages_per_minute ?? ""),
    ip: String(settings.data?.ip_messages_per_minute ?? ""),
  };

  function edit(change: Partial<Limits>) {
    save.reset();
    setEdited({ ...limits, ...change });
  }

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    save.mutate(
      {
        conversation_messages_per_minute: Number(limits.conversation),
        ip_messages_per_minute: Number(limits.ip),
      },
      {
        onSuccess: () => {
          setEdited(null);
        },
      },
    );
  }

  return (
    <section aria-label="Rate limits" className={CARD}>
    <form onSubmit={onSubmit} className="flex flex-col gap-3">
      <fieldset className="flex flex-col gap-3">
        <legend className={`${type.subheading} mb-3`}>Rate limits</legend>
        <p id="rate-limits-hint" className={type.muted}>
          How many messages Visitors may send in any one minute. Messages over a limit get the
          unavailable text instead of an answer. The Playground has no limits.
        </p>
        <div className="flex flex-wrap gap-4">
          <div>
            <label htmlFor="conversation-rate" className={field.label}>
              Messages per minute per Conversation
            </label>
            <input
              id="conversation-rate"
              type="number"
              min={1}
              aria-describedby="rate-limits-hint"
              className={`${field.inputMono} max-w-48`}
              disabled={!loaded}
              value={limits.conversation}
              onChange={(event) => {
                edit({ conversation: event.target.value });
              }}
            />
          </div>
          <div>
            <label htmlFor="ip-rate" className={field.label}>
              Messages per minute per IP address
            </label>
            <input
              id="ip-rate"
              type="number"
              min={1}
              aria-describedby="rate-limits-hint"
              className={`${field.inputMono} max-w-48`}
              disabled={!loaded}
              value={limits.ip}
              onChange={(event) => {
                edit({ ip: event.target.value });
              }}
            />
          </div>
        </div>
      </fieldset>
      <FormError message={save.error?.message} />
      <div className="flex items-center gap-3">
        <button type="submit" className={button.secondary} disabled={!loaded || save.isPending}>
          Save rate limits
        </button>
        <p role="status" className={type.muted}>
          {save.isSuccess ? "Saved. Messages over a limit get the unavailable text from now on." : ""}
        </p>
      </div>
    </form>
    </section>
  );
}

const tokens = new Intl.NumberFormat("en-GB");

/** Today's usage against the Token Budget. */
function BudgetMeter({ path }: { path: SettingsPath }) {
  const usage = useTokenUsage(path);
  if (usage.isError) return <p className={type.muted}>Today&apos;s usage could not be loaded.</p>;
  if (!usage.data) return null;
  const { tokens_used: used, daily_token_budget: budget, exhausted } = usage.data;
  const percent = Math.floor((Math.min(used, budget) / budget) * 100);
  return (
    <div className="flex flex-col gap-1">
      <Meter label="Tokens used today" value={Math.min(used, budget)} max={budget} unit="tokens" format={(n) => tokens.format(n)} />
      <p className={type.small}>{`${tokens.format(used)} of ${tokens.format(budget)} tokens used today (${String(percent)}%).`}</p>
      {exhausted && (
        <p className="text-sm font-medium text-danger">
          Today&apos;s Token Budget is spent: Visitors see the unavailable text until midnight UTC, or until you raise the budget.
        </p>
      )}
    </div>
  );
}

/** Today's Call minutes against the Call minutes budget. */
function CallMinutesMeter({ path }: { path: SettingsPath }) {
  const usage = useCallMinutes(path);
  if (usage.isError) return <p className={type.muted}>Today&apos;s Call minutes could not be loaded.</p>;
  if (!usage.data) return null;
  const { minutes_used: used, call_minutes_budget: budget, exhausted } = usage.data;
  const percent = Math.floor((Math.min(used, budget) / budget) * 100);
  return (
    <div className="flex flex-col gap-1">
      <Meter label="Call minutes today" value={Math.min(used, budget)} max={budget} unit="minutes" format={(n) => tokens.format(n)} />
      <p className={type.small}>{`${tokens.format(used)} of ${tokens.format(budget)} Call minutes used today (${String(percent)}%).`}</p>
      {exhausted && (
        <p className="text-sm font-medium text-danger">
          Today&apos;s Call minutes budget is spent: Calls are refused and Visitors are offered messaging until midnight UTC, or until
          you raise the budget.
        </p>
      )}
    </div>
  );
}

/** The Maximum Call length and the Call minutes budget, with today's Call minutes. */
function CallLimits({ path }: { path: SettingsPath }) {
  const settings = useOperationalSettings(path);
  const save = useChangeOperationalSettings(path);
  const [length, setLength] = useState<string | null>(null);
  const [budget, setBudget] = useState<string | null>(null);
  const loaded = settings.isSuccess;
  const maxMinutes = length ?? String(settings.data?.max_call_minutes ?? "");
  const budgetMinutes = budget ?? String(settings.data?.call_minutes_budget ?? "");

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    save.mutate(
      { max_call_minutes: Number(maxMinutes), call_minutes_budget: Number(budgetMinutes) },
      {
        onSuccess: () => {
          setLength(null);
          setBudget(null);
        },
      },
    );
  }

  return (
    <section aria-label="Call limits" className={CARD}>
      <form onSubmit={onSubmit} className="flex flex-col gap-3">
        <fieldset className="flex flex-col gap-3">
          <legend className={`${type.subheading} mb-3`}>Call limits</legend>
          <p id="call-limits-hint" className={type.muted}>
            The platform ends a Call at the Maximum Call length. Ended Calls count their minutes, rounded up, against the daily budget,
            which resets at midnight UTC. The Playground doesn&apos;t count.
          </p>
          <CallMinutesMeter path={path} />
          <div className="flex flex-wrap gap-3">
            <div>
              <label htmlFor="max-call-minutes" className={field.label}>
                Maximum Call length (minutes)
              </label>
              <input
                id="max-call-minutes"
                type="number"
                min={1}
                max={60}
                aria-describedby="call-limits-hint"
                className={`${field.inputMono} max-w-48`}
                disabled={!loaded}
                value={maxMinutes}
                onChange={(event) => {
                  save.reset();
                  setLength(event.target.value);
                }}
              />
            </div>
            <div>
              <label htmlFor="call-minutes-budget" className={field.label}>
                Call minutes per day
              </label>
              <input
                id="call-minutes-budget"
                type="number"
                min={1}
                aria-describedby="call-limits-hint"
                className={`${field.inputMono} max-w-48`}
                disabled={!loaded}
                value={budgetMinutes}
                onChange={(event) => {
                  save.reset();
                  setBudget(event.target.value);
                }}
              />
            </div>
          </div>
        </fieldset>
        <FormError message={save.error?.message} />
        <div className="flex items-center gap-3">
          <button type="submit" className={button.secondary} disabled={!loaded || save.isPending}>
            Save Call limits
          </button>
          <p role="status" className={type.muted}>
            {save.isSuccess ? "Saved. The new limits apply to the next Call." : ""}
          </p>
        </div>
      </form>
    </section>
  );
}

function TokenBudget({ path }: { path: SettingsPath }) {
  const settings = useOperationalSettings(path);
  const save = useChangeOperationalSettings(path);
  const [edited, setEdited] = useState<string | null>(null);
  const loaded = settings.isSuccess;
  const budget = edited ?? String(settings.data?.daily_token_budget ?? "");

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    save.mutate(
      { daily_token_budget: Number(budget) },
      {
        onSuccess: () => {
          setEdited(null);
        },
      },
    );
  }

  return (
    <section aria-label="Token Budget" className={CARD}>
    <form onSubmit={onSubmit} className="flex flex-col gap-3">
      <fieldset className="flex flex-col gap-3">
        <legend className={`${type.subheading} mb-3`}>Token Budget</legend>
        <p id="token-budget-hint" className={type.muted}>
          The budget resets at midnight UTC. The Playground doesn&apos;t count.
        </p>
        <BudgetMeter path={path} />
        <div>
          <label htmlFor="token-budget" className={field.label}>
            Tokens per day
          </label>
          <input
            id="token-budget"
            type="number"
            min={1}
            aria-describedby="token-budget-hint"
            className={`${field.inputMono} max-w-48`}
            disabled={!loaded}
            value={budget}
            onChange={(event) => {
              save.reset();
              setEdited(event.target.value);
            }}
          />
        </div>
      </fieldset>
      <FormError message={save.error?.message} />
      <div className="flex items-center gap-3">
        <button type="submit" className={button.secondary} disabled={!loaded || save.isPending}>
          Save Token Budget
        </button>
        <p role="status" className={type.muted}>
          {save.isSuccess ? "Saved. The new budget applies to the next message." : ""}
        </p>
      </div>
    </form>
    </section>
  );
}

/** The Live sample rate: the share of Visitor replies the Evaluation Model judges as Live Verdicts. */
function LiveSampleRate({ path }: { path: SettingsPath }) {
  const settings = useOperationalSettings(path);
  const save = useChangeOperationalSettings(path);
  const budget = useEvaluationBudget(path.organisation_id);
  const [edited, setEdited] = useState<string | null>(null);
  // Without an Evaluation budget no reply can be judged, so the rate can't be set.
  const unbudgeted = budget.data?.evaluation_budget_usd === null;
  const loaded = settings.isSuccess && budget.isSuccess && !unbudgeted;
  const rate = edited ?? String(settings.data?.live_sample_rate ?? "");

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    save.mutate(
      { live_sample_rate: Number(rate) },
      {
        onSuccess: () => {
          setEdited(null);
        },
      },
    );
  }

  return (
    <section aria-labelledby="live-sample-rate-heading" className={CARD}>
      <form onSubmit={onSubmit} className="flex flex-col gap-3">
        <h3 id="live-sample-rate-heading" className={type.subheading}>
          Live sample rate
        </h3>
        <p id="live-sample-rate-hint" className={type.muted}>
          The share of Visitor replies chosen at random and judged in the background by the Evaluation Model, as a Live
          Verdict in each reply&apos;s Trace. Judged by the Evaluation Model; costs count against the Evaluation budget. 0%
          judges none; the Playground is never judged.
        </p>
        {unbudgeted && (
          <Notice tone="info">
            The Organisation has no Evaluation budget, so no reply can be judged. An Owner sets one in{" "}
            <Link
              to="/organisations/$organisationId/settings/models"
              params={{ organisationId: path.organisation_id }}
              className={type.link}
            >
              Organisation settings
            </Link>
            .
          </Notice>
        )}
        {budget.isError && <Notice tone="error">The Evaluation budget could not be loaded. Try again shortly.</Notice>}
        <div>
          <label htmlFor="live-sample-rate" className={field.label}>
            Visitor replies judged (%)
          </label>
          <input
            id="live-sample-rate"
            type="number"
            min={0}
            max={100}
            step={1}
            aria-describedby="live-sample-rate-hint"
            className={`${field.inputMono} max-w-48`}
            disabled={!loaded}
            value={rate}
            onChange={(event) => {
              save.reset();
              setEdited(event.target.value);
            }}
          />
        </div>
        <FormError message={save.error?.message} />
        <div className="flex items-center gap-3">
          <button type="submit" className={button.secondary} disabled={!loaded || save.isPending}>
            Save Live sample rate
          </button>
          <p role="status" className={type.muted}>
            {save.isSuccess ? "Saved. It applies to the next Visitor reply." : ""}
          </p>
        </div>
      </form>
    </section>
  );
}

const SPOKEN_GREETING_MAX = 500;

type CallForm = { enabled: boolean; credentialId: string; voiceId: string; greeting: string };

/** The voices of the chosen credential's account, with a sample of the chosen one to play. */
function VoicePicker({
  organisationId,
  credentialId,
  voiceId,
  disabled,
  onChange,
}: {
  organisationId: string;
  credentialId: string;
  voiceId: string;
  disabled: boolean;
  onChange: (voiceId: string) => void;
}) {
  const voices = useVoices(organisationId, credentialId || null);
  if (!credentialId) return <p className={type.muted}>Choose a credential to see its voices.</p>;
  if (voices.isError) return <Notice tone="error">{voices.error.message}</Notice>;
  if (!voices.data) return <Skeleton label="Loading the voices" lines={1} />;
  const chosen = voices.data.find((voice) => voice.id === voiceId);
  return (
    <div className="flex flex-col gap-2">
      <div>
        <label htmlFor="call-voice" className={field.label}>
          Voice
        </label>
        <select
          id="call-voice"
          className={field.select}
          disabled={disabled}
          value={voiceId}
          onChange={(event) => {
            onChange(event.target.value);
          }}
        >
          <option value="">Choose a voice</option>
          {voices.data.map((voice) => (
            <option key={voice.id} value={voice.id}>
              {voice.name}
            </option>
          ))}
        </select>
        <p className={field.hint}>The voices in the credential&apos;s ElevenLabs account.</p>
      </div>
      {chosen?.sample_url && (
        <audio controls preload="none" src={chosen.sample_url} aria-label={`Sample of ${chosen.name}`} className="w-full" />
      )}
      {chosen && !chosen.sample_url && <p className={type.small}>{`${chosen.name} has no sample to play.`}</p>}
    </div>
  );
}

/** Whether Visitors can talk to the Agent in a Call, the voice-capable credential and voice it
 * speaks with, and its spoken greeting, with the Calls failing alert when the voice layer couldn't
 * start a Call. Saving sets the Agent up in the voice layer again, which clears the alert. */
function CallSettings({ path }: { path: SettingsPath }) {
  const settings = useOperationalSettings(path);
  const credentials = useCredentials(path.organisation_id);
  const save = useChangeOperationalSettings(path);
  const [edited, setEdited] = useState<CallForm | null>(null);
  const loaded = settings.isSuccess;
  const form: CallForm = edited ?? {
    enabled: settings.data?.calls_enabled ?? false,
    credentialId: settings.data?.call_credential_id ?? "",
    voiceId: settings.data?.call_voice_id ?? "",
    greeting: settings.data?.spoken_greeting ?? "",
  };
  const voiceCredentials = (credentials.data ?? []).filter((credential) => credential.capabilities.includes("voice"));
  const noVoiceCredential = credentials.isSuccess && voiceCredentials.length === 0;

  function edit(change: Partial<CallForm>) {
    save.reset();
    setEdited({ ...form, ...change });
  }

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    save.mutate(
      {
        calls_enabled: form.enabled,
        spoken_greeting: form.greeting,
        ...(form.credentialId ? { call_credential_id: form.credentialId } : {}),
        ...(form.voiceId ? { call_voice_id: form.voiceId } : {}),
      },
      {
        onSuccess: () => {
          setEdited(null);
        },
      },
    );
  }

  return (
    <section aria-labelledby="call-settings-heading" className={CARD}>
      <form onSubmit={onSubmit} className="flex flex-col gap-3">
        <h3 id="call-settings-heading" className={type.subheading}>
          Call settings
        </h3>
        <p id="call-settings-hint" className={type.muted}>
          Let Visitors talk to the Agent in a Call as well as type. It answers exactly as it does in the chat, in the
          voice you choose; Calls are held in English.
        </p>
        {noVoiceCredential && (
          <Notice tone="info">
            The Organisation has no voice-capable credential, so the Agent can&apos;t take Calls. An Owner adds an
            ElevenLabs credential in{" "}
            <Link
              to="/organisations/$organisationId/settings/credentials"
              params={{ organisationId: path.organisation_id }}
              className={type.link}
            >
              Organisation settings
            </Link>
            .
          </Notice>
        )}
        {settings.data?.calls_failing && (
          <Notice tone="error">
            Calls are failing: ElevenLabs couldn&apos;t start the Agent&apos;s last Call, so Visitors who chose Call were given
            the unavailable text and the chat. Messaging still works. Check the credential, then save the Call settings to set
            the Agent up again.
          </Notice>
        )}
        {credentials.isError && <Notice tone="error">The credentials could not be loaded. Try again shortly.</Notice>}
        <label className="flex items-center gap-2 text-sm text-ink">
          <input
            type="checkbox"
            className={field.checkbox}
            aria-describedby="call-settings-hint"
            disabled={!loaded}
            checked={form.enabled}
            onChange={(event) => {
              edit({ enabled: event.target.checked });
            }}
          />
          Visitors can call the Agent
        </label>
        <div>
          <label htmlFor="call-credential" className={field.label}>
            Credential
          </label>
          <select
            id="call-credential"
            className={field.select}
            disabled={!loaded}
            value={form.credentialId}
            onChange={(event) => {
              // Each ElevenLabs account has its own voices.
              edit({ credentialId: event.target.value, voiceId: "" });
            }}
          >
            <option value="">Choose a credential</option>
            {voiceCredentials.map((credential) => (
              <option key={credential.id} value={credential.id}>
                {credential.name}
              </option>
            ))}
          </select>
        </div>
        <VoicePicker
          organisationId={path.organisation_id}
          credentialId={form.credentialId}
          voiceId={form.voiceId}
          disabled={!loaded}
          onChange={(voiceId) => {
            edit({ voiceId });
          }}
        />
        <div>
          <label htmlFor="spoken-greeting" className={field.label}>
            Spoken greeting
          </label>
          <textarea
            id="spoken-greeting"
            aria-describedby="spoken-greeting-hint"
            rows={2}
            maxLength={SPOKEN_GREETING_MAX}
            className={field.textarea}
            disabled={!loaded}
            value={form.greeting}
            onChange={(event) => {
              edit({ greeting: event.target.value });
            }}
          />
          <p id="spoken-greeting-hint" className={field.hint}>
            What the Agent says when a Call opens a new Conversation. Leave it empty to wait for the Visitor.
          </p>
        </div>
        <FormError message={save.error?.message} />
        <div className="flex items-center gap-3">
          <button type="submit" className={button.secondary} disabled={!loaded || save.isPending}>
            Save Call settings
          </button>
          <p role="status" className={type.muted}>
            {save.isSuccess ? "Saved. Calls use these settings from now on." : ""}
          </p>
        </div>
      </form>
    </section>
  );
}

/** The Agent's Embed Snippet, once it has a Live Version, and its Operational Settings as cards: the
 * sites allowed to show it, what Visitors see when it can't answer, its daily Token Budget, with
 * today's usage, its Call limits, with today's Call minutes, its rate limits, its Live sample rate
 * and its Call settings. They apply at once, without publishing. */
export function AgentEmbed({ agent, organisationId }: { agent: Agent; organisationId: string }) {
  const path = { organisation_id: organisationId, project_id: agent.project_id, agent_id: agent.id };
  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="embed-heading" className={CARD}>
        <h2 id="embed-heading" className={type.subheading}>
          Embed Snippet
        </h2>
        {agent.live_version ? <Snippet agent={agent} /> : <p className={type.muted}>Publish the Agent to get its Embed Snippet.</p>}
      </section>
      <Notice tone="info">These Operational Settings apply straight away, without publishing, and every change is recorded in the Audit log.</Notice>
      <div className="grid gap-6 lg:grid-cols-2">
        <AllowedOrigins path={path} />
        <UnavailableText path={path} />
        <TokenBudget path={path} />
        <CallLimits path={path} />
        <RateLimits path={path} />
        <LiveSampleRate path={path} />
        <CallSettings path={path} />
      </div>
    </div>
  );
}
