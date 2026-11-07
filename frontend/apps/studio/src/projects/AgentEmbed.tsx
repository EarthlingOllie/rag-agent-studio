import { type SubmitEvent, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import type { Agent } from "./agents";
import { embedSnippet, type SnippetLayout, useAllowedOrigins, useSaveAllowedOrigins } from "./embed";
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

function AllowedOrigins({ agent, organisationId }: { agent: Agent; organisationId: string }) {
  const path = { organisation_id: organisationId, project_id: agent.project_id, agent_id: agent.id };
  const origins = useAllowedOrigins(path);
  const save = useSaveAllowedOrigins(path);
  const [edited, setEdited] = useState<string | null>(null);
  const text = edited ?? (origins.data ?? []).join("\n");
  // Until the saved list is here, saving would replace it with whatever the box holds.
  const loaded = origins.isSuccess;

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const lines = text
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    save.mutate(lines, {
      onSuccess: () => {
        setEdited(null);
      },
    });
  }

  return (
    <form onSubmit={onSubmit} className="space-y-2">
      <label htmlFor="allowed-origins" className="block text-sm font-medium">
        Allowed Origins
      </label>
      <p id="allowed-origins-hint" className="text-sm text-slate-700">
        One site per line, such as https://www.example.com. Only pages on these sites can show the
        Agent.
      </p>
      {origins.isError && <p className="text-sm text-slate-700">The Allowed Origins could not be loaded.</p>}
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

/** The Agent's Embed Snippet, once it has a Live Version, and the sites allowed to show it. */
export function AgentEmbed({ agent, organisationId }: { agent: Agent; organisationId: string }) {
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
      <AllowedOrigins agent={agent} organisationId={organisationId} />
    </section>
  );
}
