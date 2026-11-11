import { type SubmitEvent, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { button, CodeBlock, EditableList, field, Meter, Notice, Skeleton, surface, text as type } from "../design";
import type { Agent } from "./agents";
import {
  embedSnippet,
  type OperationalSettings,
  type SnippetLayout,
  useChangeOperationalSettings,
  useOperationalSettings,
  useTokenUsage,
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

/** The Agent's Embed Snippet, once it has a Live Version, and its Operational Settings as cards: the
 * sites allowed to show it, what Visitors see when it can't answer, its daily Token Budget, with
 * today's usage, and its rate limits. They apply at once, without publishing. */
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
        <RateLimits path={path} />
      </div>
    </div>
  );
}
