import { type SubmitEvent, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import type { Agent } from "./agents";
import {
  embedSnippet,
  type SnippetLayout,
  useChangeOperationalSettings,
  useOperationalSettings,
  useTokenUsage,
} from "./embed";
import { BUTTON, INPUT } from "./ProjectsPage";

function Snippet({ agent }: { agent: Agent }) {
  const [launcher, setLauncher] = useState<SnippetLayout["launcher"]>("theme");
  const [target, setTarget] = useState("#chat");
  const layout: SnippetLayout = launcher === "inline" ? { launcher, target } : { launcher };
  const snippet = embedSnippet(agent.public_id, window.location.origin, layout);
  const [copied, setCopied] = useState<string>("");

  async function copy() {
    try {
      await navigator.clipboard.writeText(snippet);
      setCopied("Copied.");
    } catch {
      setCopied("Couldn't copy. Select the snippet and copy it.");
    }
  }

  return (
    <div className="space-y-2">
      <p className="text-sm text-slate-700">
        Paste this into the pages where Visitors should chat with the Agent&apos;s Live Version.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm font-medium">
          Launcher
          <select
            value={launcher}
            onChange={(event) => {
              setCopied("");
              setLauncher(event.target.value as SnippetLayout["launcher"]);
            }}
            className={`${INPUT} mt-1 block`}
          >
            <option value="theme">The Theme&apos;s Launcher</option>
            <option value="bubble">Bubble in the corner</option>
            <option value="inline">Inline in a container</option>
          </select>
        </label>
        {launcher === "inline" && (
          <label className="text-sm font-medium">
            Container selector
            <input
              value={target}
              onChange={(event) => {
                setCopied("");
                setTarget(event.target.value);
              }}
              spellCheck={false}
              className={`${INPUT} mt-1 block font-mono`}
            />
          </label>
        )}
      </div>
      <pre
        aria-label="Embed Snippet"
        className="overflow-x-auto rounded border border-slate-300 bg-slate-50 p-2 text-xs"
      >
        <code>{snippet}</code>
      </pre>
      <div className="flex items-center gap-3">
        <button
          type="button"
          className={BUTTON}
          onClick={() => {
            void copy();
          }}
        >
          Copy snippet
        </button>
        <p role="status" className="text-sm text-slate-700">
          {copied}
        </p>
      </div>
    </div>
  );
}

type SettingsPath = { organisation_id: string; project_id: string; agent_id: string };

function AllowedOrigins({ path }: { path: SettingsPath }) {
  const settings = useOperationalSettings(path);
  const save = useChangeOperationalSettings(path);
  const [edited, setEdited] = useState<string | null>(null);
  const text = edited ?? (settings.data?.allowed_origins ?? []).join("\n");
  // Until the saved list is here, saving would replace it with whatever the box holds.
  const loaded = settings.isSuccess;

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const lines = text
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    save.mutate(
      { allowed_origins: lines },
      {
        onSuccess: () => {
          setEdited(null);
        },
      },
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-2">
      <label htmlFor="allowed-origins" className="block text-sm font-medium">
        Allowed Origins
      </label>
      <p id="allowed-origins-hint" className="text-sm text-slate-700">
        One site per line, such as https://www.example.com, https://*.example.com for all its
        subdomains, or http://localhost:3000 (http://localhost:* for any port) while developing.
        Only pages on these sites can show the Agent.
      </p>
      {settings.isError && (
        <p className="text-sm text-slate-700">The Operational Settings could not be loaded.</p>
      )}
      <textarea
        id="allowed-origins"
        aria-describedby="allowed-origins-hint"
        rows={3}
        className={INPUT}
        disabled={!loaded}
        value={text}
        onChange={(event) => {
          save.reset();
          setEdited(event.target.value);
        }}
      />
      <FormError message={save.error?.message} />
      <div className="flex items-center gap-3">
        <button type="submit" className={BUTTON} disabled={!loaded || save.isPending}>
          Save Allowed Origins
        </button>
        <p role="status" className="text-sm text-slate-700">
          {save.isSuccess ? "Saved. Pages on these sites can show the Agent now." : ""}
        </p>
      </div>
    </form>
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
    <form onSubmit={onSubmit} className="space-y-2">
      <label htmlFor="unavailable-text" className="block text-sm font-medium">
        Unavailable text
      </label>
      <p id="unavailable-text-hint" className="text-sm text-slate-700">
        What Visitors see when the Agent can&apos;t answer. Leave it empty for the default.
      </p>
      <textarea
        id="unavailable-text"
        aria-describedby="unavailable-text-hint"
        rows={2}
        maxLength={UNAVAILABLE_TEXT_MAX}
        className={INPUT}
        disabled={!loaded}
        value={text}
        onChange={(event) => {
          save.reset();
          setEdited(event.target.value);
        }}
      />
      <FormError message={save.error?.message} />
      <div className="flex items-center gap-3">
        <button type="submit" className={BUTTON} disabled={!loaded || save.isPending}>
          Save unavailable text
        </button>
        <p role="status" className="text-sm text-slate-700">
          {save.isSuccess ? "Saved. Visitors see it from their next message." : ""}
        </p>
      </div>
    </form>
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
    <form onSubmit={onSubmit} className="space-y-2">
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Rate limits</legend>
        <p id="rate-limits-hint" className="text-sm text-slate-700">
          How many messages Visitors may send in any one minute. Messages over a limit get the
          unavailable text instead of an answer. The Playground has no limits.
        </p>
        <div className="flex flex-wrap gap-4">
          <div>
            <label htmlFor="conversation-rate" className="block text-sm">
              Messages per minute per Conversation
            </label>
            <input
              id="conversation-rate"
              type="number"
              min={1}
              aria-describedby="rate-limits-hint"
              className={INPUT}
              disabled={!loaded}
              value={limits.conversation}
              onChange={(event) => {
                edit({ conversation: event.target.value });
              }}
            />
          </div>
          <div>
            <label htmlFor="ip-rate" className="block text-sm">
              Messages per minute per IP address
            </label>
            <input
              id="ip-rate"
              type="number"
              min={1}
              aria-describedby="rate-limits-hint"
              className={INPUT}
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
        <button type="submit" className={BUTTON} disabled={!loaded || save.isPending}>
          Save rate limits
        </button>
        <p role="status" className="text-sm text-slate-700">
          {save.isSuccess ? "Saved. Messages over a limit get the unavailable text from now on." : ""}
        </p>
      </div>
    </form>
  );
}

const tokens = new Intl.NumberFormat("en-GB");

/** Today's usage against the Token Budget. */
function BudgetMeter({ path }: { path: SettingsPath }) {
  const usage = useTokenUsage(path);
  if (usage.isError) return <p className="text-sm text-slate-700">Today&apos;s usage could not be loaded.</p>;
  if (!usage.data) return null;
  const { tokens_used: used, daily_token_budget: budget, exhausted } = usage.data;
  const shown = Math.min(used, budget);
  const percent = Math.floor((shown / budget) * 100);
  return (
    <div className="space-y-1">
      <div
        role="progressbar"
        aria-label="Tokens used today"
        aria-valuemin={0}
        aria-valuemax={budget}
        aria-valuenow={shown}
        className="h-2 w-full max-w-md overflow-hidden rounded bg-slate-200"
      >
        <div
          className={`h-full ${exhausted ? "bg-red-700" : "bg-slate-700"}`}
          style={{ width: `${String(percent)}%` }}
        />
      </div>
      <p className="text-sm text-slate-700">
        {`${tokens.format(used)} of ${tokens.format(budget)} tokens used today (${String(percent)}%).`}
      </p>
      {exhausted && (
        <p className="text-sm font-medium text-red-800">
          Today&apos;s Token Budget is spent: Visitors see the unavailable text until midnight UTC, or until you
          raise the budget.
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
    <form onSubmit={onSubmit} className="space-y-2">
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Token Budget</legend>
        <p id="token-budget-hint" className="text-sm text-slate-700">
          The budget resets at midnight UTC. The Playground doesn&apos;t count.
        </p>
        <BudgetMeter path={path} />
        <div>
          <label htmlFor="token-budget" className="block text-sm">
            Tokens per day
          </label>
          <input
            id="token-budget"
            type="number"
            min={1}
            aria-describedby="token-budget-hint"
            className={INPUT}
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
        <button type="submit" className={BUTTON} disabled={!loaded || save.isPending}>
          Save Token Budget
        </button>
        <p role="status" className="text-sm text-slate-700">
          {save.isSuccess ? "Saved. The new budget applies to the next message." : ""}
        </p>
      </div>
    </form>
  );
}

/** The Agent's Embed Snippet, once it has a Live Version, and its Operational Settings: the
 * sites allowed to show it, what Visitors see when it can't answer, its rate limits and its daily
 * Token Budget, with today's usage. They apply at once, without publishing. */
export function AgentEmbed({ agent, organisationId }: { agent: Agent; organisationId: string }) {
  const path = { organisation_id: organisationId, project_id: agent.project_id, agent_id: agent.id };
  return (
    <section aria-labelledby="embed-heading" className="space-y-3">
      <h2 id="embed-heading" className="text-lg font-semibold">
        Embed
      </h2>
      {agent.live_version ? (
        <Snippet agent={agent} />
      ) : (
        <p className="text-sm text-slate-700">Publish the Agent to get its Embed Snippet.</p>
      )}
      <h3 className="font-semibold">Operational Settings</h3>
      <p className="text-sm text-slate-700">
        These apply straight away, without publishing, and every change is recorded in the Audit
        log.
      </p>
      <AllowedOrigins path={path} />
      <UnavailableText path={path} />
      <RateLimits path={path} />
      <TokenBudget path={path} />
    </section>
  );
}
