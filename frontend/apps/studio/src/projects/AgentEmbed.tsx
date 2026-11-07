import { type SubmitEvent, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import type { Agent } from "./agents";
import { embedSnippet, useChangeOperationalSettings, useOperationalSettings } from "./embed";
import { BUTTON, INPUT } from "./ProjectsPage";

function Snippet({ agent }: { agent: Agent }) {
  const snippet = embedSnippet(agent.public_id);
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

/** The Agent's Embed Snippet, once it has a Live Version, and its Operational Settings: the
 * sites allowed to show it and what Visitors see when it can't answer. They apply at once,
 * without publishing. */
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
    </section>
  );
}
