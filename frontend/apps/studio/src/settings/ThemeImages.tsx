import { type ChangeEvent, useId } from "react";

import { type ThemeImage, type ThemeImageKind, useThemeImage } from "./themeImages";

/** The image types the API accepts, for the file picker. */
const ACCEPT = "image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp";
const BUTTON = "rounded border border-slate-400 px-3 py-1.5 text-sm font-medium hover:bg-slate-50 disabled:text-slate-500";

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
    <div className="space-y-2 rounded border border-slate-200 p-3">
      <h4 className="text-sm font-medium">{title}</h4>
      <p className="text-xs text-slate-700">{hint}</p>
      <div className="flex min-h-12 items-center gap-3">
        {image ? (
          <>
            <img src={image.url} alt={`Current ${noun}`} className="h-12 max-w-24 rounded border border-slate-200 object-contain" />
            <span className="text-sm text-slate-700">{describe(image)}</span>
          </>
        ) : (
          <span className="text-sm text-slate-700">No {noun} yet.</span>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <label className={`${BUTTON} cursor-pointer has-[:disabled]:cursor-not-allowed has-[:disabled]:text-slate-500 has-[:focus-visible]:outline-2`}>
          {pick}
          <input type="file" accept={ACCEPT} aria-describedby={statusId} disabled={!isOwner || busy} onChange={onChange} className="sr-only" />
        </label>
        {isOwner && image && (
          <button
            type="button"
            className={BUTTON}
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
        {action.phase === "uploading" && <span className="text-slate-700">Uploading…</span>}
        {action.phase === "uploaded" && <span className="text-green-900">{title} saved. The widget uses it now.</span>}
        {action.phase === "removed" && <span className="text-green-900">{title} removed.</span>}
      </div>
      {action.phase === "failed" && (
        <p role="alert" className="text-sm text-red-800">
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
    <section aria-labelledby="theme-images-heading" className="space-y-3">
      <h3 id="theme-images-heading" className="text-base font-semibold">
        Logo and avatar
      </h3>
      <p className="text-sm text-slate-700">PNG, JPEG or WebP, up to 1 MB. Images apply as soon as they are uploaded.</p>
      <div className="grid gap-4 sm:grid-cols-2">
        <ImageField organisationId={organisationId} kind="logo" image={logo} isOwner={isOwner} />
        <ImageField organisationId={organisationId} kind="avatar" image={avatar} isOwner={isOwner} />
      </div>
    </section>
  );
}
