import { type ChangeEvent, useId } from "react";

import { button, surface, text } from "../design";
import { type ThemeImage, type ThemeImageKind, useThemeImage } from "./themeImages";

/** The image types the API accepts, for the file picker. */
const ACCEPT = "image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp";


const LABELS: Record<ThemeImageKind, { title: string; noun: string; hint: string }> = {
  logo: { title: "Logo", noun: "logo", hint: "Shown in the widget's header." },
  avatar: { title: "Avatar", noun: "avatar", hint: "The default Agent avatar, beside the Agent's name." },
};

/** "PNG, 2.0 KB": images are at most 1 MB, so kilobytes always read well. */
function describe(image: ThemeImage): string {
  return `${image.content_type.replace("image/", "").toUpperCase()}, ${(image.size_bytes / 1024).toFixed(1)} KB`;
}

function ImageField({
  organisationId,
  kind,
  image,
  isOwner,
}: {
  organisationId: string;
  kind: ThemeImageKind;
  image: ThemeImage | null;
  isOwner: boolean;
}) {
  const { action, upload, remove } = useThemeImage(organisationId, kind);
  const { title, noun, hint } = LABELS[kind];
  const statusId = useId();
  const busy = action.phase === "uploading" || action.phase === "removing";
  const pick = `${image ? "Replace" : "Upload"} ${noun}`;

  function onChange(event: ChangeEvent<HTMLInputElement>) {
    // A file input always has a file list; it is only null on other input types. This one
    // takes a single file, so the loop runs at most once.
    const files = [...(event.target.files as FileList)];
    event.target.value = "";
    for (const file of files) void upload(file);
  }

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-line-soft p-4">
      <h4 className="text-sm font-medium text-ink">{title}</h4>
      <p className={text.small}>{hint}</p>
      <div className="flex min-h-12 items-center gap-3">
        {image ? (
          <>
            <img src={image.url} alt={`Current ${noun}`} className="h-12 max-w-24 rounded-lg border border-line object-contain" />
            <span className="font-mono text-[13px] text-muted">{describe(image)}</span>
          </>
        ) : (
          <span className={text.muted}>No {noun} yet.</span>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <label
          className={`${button.secondary} cursor-pointer has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-50 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accent`}
        >
          {pick}
          <input type="file" accept={ACCEPT} aria-describedby={statusId} disabled={!isOwner || busy} onChange={onChange} className="sr-only" />
        </label>
        {isOwner && image && (
          <button
            type="button"
            className={button.danger}
            disabled={busy}
            onClick={() => {
              void remove();
            }}
          >
            {action.phase === "removing" ? "Removing…" : `Remove ${noun}`}
          </button>
        )}
      </div>
      <div id={statusId} role="status" aria-label={title} className="text-sm">
        {action.phase === "uploading" && <span className="text-muted">Uploading…</span>}
        {action.phase === "uploaded" && <span className="text-accent-ink">{title} saved. The widget uses it now.</span>}
        {action.phase === "removed" && <span className="text-accent-ink">{title} removed.</span>}
      </div>
      {action.phase === "failed" && (
        <p role="alert" className="text-sm text-danger">
          {action.message}
        </p>
      )}
    </div>
  );
}

/** Owners upload, replace and remove the Theme's logo and default avatar; everyone sees them. */
export function ThemeImages({
  organisationId,
  logo,
  avatar,
  isOwner,
}: {
  organisationId: string;
  logo: ThemeImage | null;
  avatar: ThemeImage | null;
  isOwner: boolean;
}) {
  return (
    <section aria-labelledby="theme-images-heading" className={`${surface.panel} flex flex-col gap-4`}>
      <h3 id="theme-images-heading" className={text.subheading}>
        Logo and avatar
      </h3>
      <p className={text.muted}>PNG, JPEG or WebP, up to 1 MB. Images apply as soon as they are uploaded.</p>
      <div className="grid gap-4 sm:grid-cols-2">
        <ImageField organisationId={organisationId} kind="logo" image={logo} isOwner={isOwner} />
        <ImageField organisationId={organisationId} kind="avatar" image={avatar} isOwner={isOwner} />
      </div>
    </section>
  );
}
