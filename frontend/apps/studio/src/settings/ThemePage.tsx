import {
  AccentLink,
  ChatWindow,
  COLOUR_TOKENS,
  type ColourScheme,
  type ColourToken,
  Composer,
  contrastWarnings,
  fontStylesheetUrl,
  Launcher,
  MessageBubble,
  MutedText,
  ThemeScope,
} from "@studio/ui";
import { type ReactNode, useId, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { type ThemeFont, type ThemeSettings, useSaveTheme, useTheme, useThemeFonts } from "./theme";
import { ThemeImages } from "./ThemeImages";
import type { ThemeImage } from "./themeImages";

const HEX = /^#[0-9a-fA-F]{6}$/;
const MAX_RADIUS = 24;
const INPUT = "rounded border border-slate-400 px-2 py-1 text-sm disabled:bg-slate-100 aria-[invalid=true]:border-red-700";
const BUTTON = "rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:bg-slate-500";
const FIELD_ERROR = "text-xs text-red-800";

type Validity = (field: string, valid: boolean) => void;

/** A hex field and a colour picker for one value of one colour token. */
function ColourField({
  label,
  value,
  onChange,
  onValidity,
}: {
  label: string;
  value: string;
  onChange: (hex: string) => void;
  onValidity: Validity;
}) {
  const [text, setText] = useState(value);
  const id = useId();
  const valid = HEX.test(text);
  const apply = (next: string) => {
    setText(next);
    const ok = HEX.test(next);
    onValidity(label, ok);
    if (ok) onChange(next.toLowerCase());
  };
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-xs font-medium text-slate-700">
        {label}
      </label>
      <div className="flex items-center gap-2">
        <input
          type="color"
          aria-label={`${label} colour picker`}
          value={value}
          onInput={(event) => {
            apply(event.currentTarget.value);
          }}
          onChange={() => undefined}
          className="h-8 w-10 cursor-pointer rounded border border-slate-400 bg-white p-0.5 disabled:cursor-not-allowed"
        />
        <input
          id={id}
          value={text}
          aria-invalid={!valid}
          aria-describedby={valid ? undefined : `${id}-error`}
          onChange={(event) => {
            apply(event.target.value);
          }}
          spellCheck={false}
          className={`${INPUT} w-24 font-mono`}
        />
      </div>
      {!valid && (
        <p id={`${id}-error`} className={FIELD_ERROR}>
          Use a colour like #1a2b3c.
        </p>
      )}
    </div>
  );
}

function RadiusField({ value, onChange, onValidity }: { value: number; onChange: (radius: number) => void; onValidity: Validity }) {
  const [text, setText] = useState(String(value));
  const id = useId();
  const parse = (raw: string) => (/^\d+$/.test(raw) && Number(raw) <= MAX_RADIUS ? Number(raw) : undefined);
  const valid = parse(text) !== undefined;
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-sm font-medium">
        Corner radius (px)
      </label>
      <input
        id={id}
        type="number"
        min={0}
        max={MAX_RADIUS}
        step={1}
        value={text}
        aria-invalid={!valid}
        aria-describedby={valid ? undefined : `${id}-error`}
        onChange={(event) => {
          const raw = event.target.value;
          setText(raw);
          const radius = parse(raw);
          onValidity("radius", radius !== undefined);
          if (radius !== undefined) onChange(radius);
        }}
        className={`${INPUT} w-24`}
      />
      {!valid && (
        <p id={`${id}-error`} className={FIELD_ERROR}>
          Use a whole number from 0 to {MAX_RADIUS}.
        </p>
      )}
    </div>
  );
}

function Choices<T extends string>({
  label,
  name,
  value,
  options,
  onChange,
}: {
  label: string;
  name: string;
  value: T;
  options: readonly { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  const id = useId();
  return (
    <div role="radiogroup" aria-labelledby={id} className="space-y-1">
      <span id={id} className="block text-sm font-medium">
        {label}
      </span>
      <div className="flex flex-wrap gap-4">
        {options.map((option) => (
          <label key={option.value} className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name={`${name}-${id}`}
              value={option.value}
              checked={value === option.value}
              onChange={() => {
                onChange(option.value);
              }}
            />
            {option.label}
          </label>
        ))}
      </div>
    </div>
  );
}

const MODES = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "auto", label: "Automatic" },
] as const;
const LAUNCHERS = [
  { value: "bubble", label: "Floating bubble" },
  { value: "inline", label: "Inline container" },
] as const;
const POSITIONS = [
  { value: "bottom-right", label: "Bottom right" },
  { value: "bottom-left", label: "Bottom left" },
] as const;
const SCHEMES = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
] as const;

/** The widget as a Visitor will see it, built from the same primitives the widget renders. */
function WidgetPreview({ theme, scheme, images }: { theme: ThemeSettings; scheme: ColourScheme; images: SavedImages }) {
  const [open, setOpen] = useState(true);
  const bubble = theme.launcher_type === "bubble";
  const chat = (
    <ChatWindow
      agentName="Assistant"
      logoUrl={images.logo?.url}
      avatarUrl={images.avatar?.url}
      composer={
        <Composer
          onSend={() => {
            // The preview's message box is for show.
          }}
        />
      }
    >
      <MessageBubble from="agent">Hi! How can I help you today?</MessageBubble>
      <MessageBubble from="visitor">What are your opening hours?</MessageBubble>
      <MessageBubble from="agent">
        We are open 9 to 5, Monday to Friday.
        <MutedText>
          Source: <AccentLink href="#opening-hours">Opening hours, page 2</AccentLink>
        </MutedText>
      </MessageBubble>
    </ChatWindow>
  );
  return (
    <ThemeScope
      theme={theme}
      scheme={scheme}
      label={`Widget preview (${scheme})`}
      style={{
        position: "relative",
        minHeight: 520,
        padding: 16,
        borderRadius: 8,
        border: "1px dashed #94a3b8",
        background: scheme === "dark" ? "#0f172a" : "#f1f5f9",
      }}
    >
      {bubble ? (
        <>
          {open && (
            <div style={{ position: "absolute", bottom: 84, width: "min(340px, calc(100% - 32px))", [theme.launcher_position === "bottom-left" ? "left" : "right"]: 16 }}>
              {chat}
            </div>
          )}
          <Launcher
            open={open}
            position={theme.launcher_position}
            onToggle={() => {
              setOpen(!open);
            }}
          />
        </>
      ) : (
        chat
      )}
    </ThemeScope>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <h3 className="text-base font-semibold">{title}</h3>
      {children}
    </section>
  );
}

interface SavedImages {
  logo: ThemeImage | null;
  avatar: ThemeImage | null;
}

function ThemeEditor({
  saved,
  images,
  fonts,
  isOwner,
  organisationId,
}: {
  saved: ThemeSettings;
  images: SavedImages;
  fonts: ThemeFont[];
  isOwner: boolean;
  organisationId: string;
}) {
  const save = useSaveTheme(organisationId);
  const [draft, setDraft] = useState<ThemeSettings>(saved);
  const [invalid, setInvalid] = useState<Record<string, boolean>>({});
  const [previewScheme, setPreviewScheme] = useState<ColourScheme>("light");
  const fontId = useId();

  const update = (change: Partial<ThemeSettings>) => {
    save.reset();
    setDraft((current) => ({ ...current, ...change }));
  };
  const setColour = (token: ColourToken, scheme: ColourScheme, hex: string) => {
    save.reset();
    setDraft((current) => ({
      ...current,
      colours: { ...current.colours, [token]: { ...current.colours[token], [scheme]: hex } },
    }));
  };
  const onValidity: Validity = (field, valid) => {
    setInvalid((current) => ({ ...current, [field]: !valid }));
  };
  const hasInvalid = Object.values(invalid).some(Boolean);
  const warnings = contrastWarnings(draft);
  const scheme: ColourScheme = draft.mode === "auto" ? previewScheme : draft.mode;

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,24rem)]">
      <link rel="stylesheet" href={fontStylesheetUrl(draft.font)} />
      <div className="space-y-8">
        <form
          aria-label="Theme"
          className="space-y-6"
          onSubmit={(event) => {
            event.preventDefault();
            save.mutate(draft);
          }}
        >
          {!isOwner && <p className="rounded bg-slate-100 px-3 py-2 text-sm text-slate-700">Only Owners can change the Theme.</p>}
          <fieldset disabled={!isOwner} className="space-y-6">
            <Section title="Colours">
              <p className="text-sm text-slate-700">Each colour has a value for light mode and one for dark mode.</p>
              <div className="grid gap-4 sm:grid-cols-2">
                {COLOUR_TOKENS.map(({ token, label }) => (
                  <div key={token} className="flex flex-wrap gap-4 rounded border border-slate-200 p-3">
                    {(["light", "dark"] as const).map((colourScheme) => (
                      <ColourField
                        key={colourScheme}
                        label={`${label} (${colourScheme})`}
                        value={draft.colours[token][colourScheme]}
                        onChange={(hex) => {
                          setColour(token, colourScheme, hex);
                        }}
                        onValidity={onValidity}
                      />
                    ))}
                  </div>
                ))}
              </div>
            </Section>
            <Section title="Shape and type">
              <RadiusField
                value={draft.radius}
                onChange={(radius) => {
                  update({ radius });
                }}
                onValidity={onValidity}
              />
              <div className="space-y-1">
                <label htmlFor={fontId} className="block text-sm font-medium">
                  Font
                </label>
                <select
                  id={fontId}
                  value={draft.font}
                  onChange={(event) => {
                    update({ font: event.target.value as ThemeSettings["font"] });
                  }}
                  className={INPUT}
                >
                  {fonts.map((font) => (
                    <option key={font.family} value={font.family}>
                      {font.family} ({font.category})
                    </option>
                  ))}
                </select>
              </div>
            </Section>
            <Section title="Mode and launcher">
              <Choices
                label="Mode"
                name="mode"
                value={draft.mode}
                options={MODES}
                onChange={(mode) => {
                  update({ mode });
                }}
              />
              <Choices
                label="Launcher"
                name="launcher"
                value={draft.launcher_type}
                options={LAUNCHERS}
                onChange={(launcher_type) => {
                  update({ launcher_type });
                }}
              />
              {draft.launcher_type === "bubble" && (
                <Choices
                  label="Bubble position"
                  name="position"
                  value={draft.launcher_position}
                  options={POSITIONS}
                  onChange={(launcher_position) => {
                    update({ launcher_position });
                  }}
                />
              )}
            </Section>
          </fieldset>
          <div role="status" aria-label="Contrast" className="space-y-2">
            {warnings.length > 0 && (
              <div className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                <p className="font-medium">Some colours fail WCAG AA contrast. You can still save.</p>
                <ul className="mt-1 list-disc pl-5">
                  {warnings.map((warning) => (
                    <li key={`${warning.scheme}-${warning.foreground}`}>{warning.message}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
          {isOwner && (
            <div className="space-y-3">
              <FormError message={save.isError ? "Something went wrong. Try again." : undefined} />
              {save.isSuccess && (
                <p role="status" aria-label="Saved" className="rounded border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-900">
                  Theme saved. The widget uses it now.
                </p>
              )}
              <button type="submit" className={BUTTON} disabled={hasInvalid || save.isPending}>
                {save.isPending ? "Saving…" : "Save Theme"}
              </button>
            </div>
          )}
        </form>
        <ThemeImages organisationId={organisationId} logo={images.logo} avatar={images.avatar} isOwner={isOwner} />
      </div>
      <section aria-labelledby="preview-heading" className="space-y-3 lg:sticky lg:top-6 lg:self-start">
        <h3 id="preview-heading" className="text-base font-semibold">
          Preview
        </h3>
        {draft.mode === "auto" && (
          <Choices label="Preview colours" name="preview" value={previewScheme} options={SCHEMES} onChange={setPreviewScheme} />
        )}
        <WidgetPreview theme={draft} scheme={scheme} images={images} />
      </section>
    </div>
  );
}

/** The Theme tab: every Member sees the Theme and its preview; Owners edit and save it. */
export function ThemePage({ organisationId, isOwner }: { organisationId: string; isOwner: boolean }) {
  const theme = useTheme(organisationId);
  const fonts = useThemeFonts();
  let body: ReactNode;
  if (theme.isError || fonts.isError) {
    body = <FormError message="The Theme could not be loaded. Try again." />;
  } else if (theme.data && fonts.data) {
    const { colours, radius, font, mode, launcher_type, launcher_position, logo, avatar } = theme.data;
    const saved = { colours, radius, font, mode, launcher_type, launcher_position };
    body = (
      <ThemeEditor
        key={organisationId}
        saved={saved}
        images={{ logo, avatar }}
        fonts={fonts.data}
        isOwner={isOwner}
        organisationId={organisationId}
      />
    );
  } else {
    body = <p className="text-sm text-slate-700">Loading the Theme…</p>;
  }
  return (
    <section aria-labelledby="theme-heading" className="space-y-4">
      <div>
        <h2 id="theme-heading" className="text-lg font-semibold">
          Theme
        </h2>
        <p className="text-sm text-slate-700">How embedded Agents look to Visitors. Changes apply as soon as they are saved.</p>
      </div>
      {body}
    </section>
  );
}
