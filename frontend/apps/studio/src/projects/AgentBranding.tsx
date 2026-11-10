import { COLOUR_TOKENS, type ColourToken } from "@studio/ui";
import { type ChangeEvent, type SubmitEvent, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { button, field, surface, text } from "../design";
import { useTheme } from "../settings/theme";
import type { Agent } from "./agents";
import { type ColourValue, type ThemeOverride, useAgentAvatar, useSaveOverrideColours, useThemeOverride } from "./branding";

const HEX = /^#[0-9a-fA-F]{6}$/;
const ACCEPT = "image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp";

type Row = { on: boolean; light: string; dark: string };
type Rows = Record<ColourToken, Row>;

function rowsFrom(saved: ThemeOverride, theme: Record<ColourToken, ColourValue>): Rows {
  const rows = {} as Rows;
  for (const { token } of COLOUR_TOKENS) {
    const own = saved.colours[token];
    rows[token] = { on: own !== undefined, ...(own ?? theme[token]) };
  }
  return rows;
}

function Colours({
  saved,
  theme,
  path,
  isOwner,
}: {
  saved: ThemeOverride;
  theme: Record<ColourToken, ColourValue>;
  path: { organisation_id: string; project_id: string; agent_id: string };
  isOwner: boolean;
}) {
  const save = useSaveOverrideColours(path);
  const [edited, setEdited] = useState<Rows | null>(null);
  const rows = edited ?? rowsFrom(saved, theme);
  const valid = COLOUR_TOKENS.every(({ token }) => !rows[token].on || (HEX.test(rows[token].light) && HEX.test(rows[token].dark)));

  function change(token: ColourToken, row: Partial<Row>) {
    save.reset();
    setEdited({ ...rows, [token]: { ...rows[token], ...row } });
  }

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const colours: Record<string, ColourValue> = {};
    for (const { token } of COLOUR_TOKENS) {
      const { on, light, dark } = rows[token];
      if (on) colours[token] = { light: light.toLowerCase(), dark: dark.toLowerCase() };
    }
    save.mutate(colours, {
      onSuccess: () => {
        setEdited(null);
      },
    });
  }

  return (
    <form onSubmit={onSubmit} aria-label="Colour override" className="space-y-2">
      <p className={text.muted}>
        Tick a colour to give this Agent its own; the others follow the Organisation&apos;s Theme.
      </p>
      <fieldset disabled={!isOwner} className="grid gap-2 sm:grid-cols-2">
        <legend className="sr-only">Colours</legend>
        {COLOUR_TOKENS.map(({ token, label }) => {
          const row = rows[token];
          return (
            <div key={token} className="space-y-2 rounded-xl border border-line p-3">
              <label className="flex items-center gap-2 text-sm font-medium text-ink-2">
                <input
                  type="checkbox"
                  className={field.checkbox}
                  checked={row.on}
                  onChange={(event) => {
                    change(token, { on: event.target.checked });
                  }}
                />
                Override {label.toLowerCase()}
              </label>
              {row.on && (
                <div className="flex flex-wrap gap-3">
                  {(["light", "dark"] as const).map((scheme) => (
                    <label key={scheme} className={field.hint}>
                      {`${label}, ${scheme}`}
                      <input
                        value={row[scheme]}
                        aria-invalid={!HEX.test(row[scheme])}
                        spellCheck={false}
                        onChange={(event) => {
                          change(token, { [scheme]: event.target.value });
                        }}
                        className={`${field.inputMono} w-28`}
                      />
                    </label>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </fieldset>
      {!valid && <p className={field.error}>Use colours like #1a2b3c.</p>}
      <FormError message={save.error?.message} />
      {isOwner && (
        <div className="flex items-center gap-3">
          <button type="submit" className={button.primary} disabled={!valid || save.isPending}>
            Save colours
          </button>
          <p role="status" className={text.muted}>
            {save.isSuccess ? "Saved. The widget uses these colours now." : ""}
          </p>
        </div>
      )}
    </form>
  );
}

function Avatar({
  saved,
  path,
  isOwner,
}: {
  saved: ThemeOverride;
  path: { organisation_id: string; project_id: string; agent_id: string };
  isOwner: boolean;
}) {
  const { action, upload, remove } = useAgentAvatar(path);
  const busy = action.phase === "uploading" || action.phase === "removing";
  const image = saved.avatar;

  function onChange(event: ChangeEvent<HTMLInputElement>) {
    const files = [...(event.target.files as FileList)];
    event.target.value = "";
    for (const file of files) void upload(file);
  }

  return (
    <div className="space-y-2">
      <h3 className={field.label}>Avatar</h3>
      <div className="flex min-h-12 items-center gap-3">
        {image ? (
          <img src={image.url} alt="The Agent's avatar" className="h-12 w-12 rounded-full border border-line object-cover" />
        ) : (
          <span className={text.muted}>No avatar of its own: the widget shows the Live Version&apos;s or the Theme&apos;s.</span>
        )}
      </div>
      {isOwner && (
        <div className="flex flex-wrap items-center gap-2">
          <label className={`${button.secondary} cursor-pointer has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-50 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent`}>
            {image ? "Replace avatar" : "Upload avatar"}
            <input type="file" accept={ACCEPT} disabled={busy} onChange={onChange} className="sr-only" />
          </label>
          {image && (
            <button
              type="button"
              className={button.danger}
              disabled={busy}
              onClick={() => {
                void remove();
              }}
            >
              Remove avatar
            </button>
          )}
        </div>
      )}
      <p role="status" aria-label="Avatar" className={text.muted}>
        {action.phase === "uploading" && "Uploading…"}
        {action.phase === "removing" && "Removing…"}
        {action.phase === "uploaded" && "Avatar saved. The widget uses it now."}
        {action.phase === "removed" && "Avatar removed."}
      </p>
      {action.phase === "failed" && (
        <p role="alert" className={field.error}>
          {action.message}
        </p>
      )}
    </div>
  );
}

/**
 * The Agent's Theme override: colours and an avatar of its own in the widget. Owners change it
 * (as they change the Theme); Editors see it. It isn't part of the Draft, so it isn't versioned
 * and applies to the widget without publishing.
 */
export function AgentBranding({ agent, organisationId, isOwner }: { agent: Agent; organisationId: string; isOwner: boolean }) {
  const path = { organisation_id: organisationId, project_id: agent.project_id, agent_id: agent.id };
  const saved = useThemeOverride(path);
  const theme = useTheme(organisationId);

  let body;
  if (saved.isError || theme.isError) body = <p role="alert">The widget branding could not be loaded.</p>;
  else if (!saved.data || !theme.data) body = <p role="status">Loading the widget branding…</p>;
  else
    body = (
      <>
        <Colours saved={saved.data} theme={theme.data.colours} path={path} isOwner={isOwner} />
        <Avatar saved={saved.data} path={path} isOwner={isOwner} />
      </>
    );

  return (
    <section aria-labelledby="branding-heading" className={`${surface.panel} flex flex-col gap-4`}>
      <h2 id="branding-heading" className={text.subheading}>
        Theme override
      </h2>
      <p className={text.muted}>
        {isOwner
          ? "Changes apply to the widget at once, without publishing."
          : "Only Owners can change the widget branding. Changes apply without publishing."}
      </p>
      {body}
    </section>
  );
}
