/**
 * Class recipes: the Studio's shared Tailwind class lists, built only from design tokens
 * (design/tokens.css). Pages use these instead of their own BUTTON / INPUT / TAB strings, so the
 * look stays consistent and changes in one place. See docs/design/README.md.
 */

/** Shared by every button. A button that opens a menu turns soft green while the menu is open. */
const CONTROL = "aria-expanded:bg-accent-soft aria-expanded:text-accent-ink inline-flex items-center justify-center gap-2 whitespace-nowrap font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50";

/** Buttons are pills. One primary per view (Publish, Upload, Send, Save). */
export const button = {
  primary: `${CONTROL} h-9 rounded-full bg-accent px-4 text-sm text-on-accent hover:bg-accent-hover`,
  secondary: `${CONTROL} h-9 rounded-full border border-field bg-surface px-4 text-sm text-ink hover:bg-sunken`,
  ghost: `${CONTROL} h-9 rounded-full px-3 text-sm text-ink hover:bg-sunken`,
  danger: `${CONTROL} h-9 rounded-full border border-field bg-surface px-4 text-sm text-danger hover:bg-danger-soft`,
  /** The confirming button of a destructive ConfirmDialog: the one filled danger button. */
  dangerFilled: `${CONTROL} h-9 rounded-full bg-danger px-4 text-sm text-on-danger hover:opacity-90`,
  /** Small text action inside a row or card ("Reset", "New conversation"). */
  quiet: `${CONTROL} rounded-md px-1 text-sm text-ink hover:text-accent`,
  /** Icon-only; always give it an aria-label. */
  icon: `${CONTROL} size-9 shrink-0 rounded-full border border-field bg-surface text-muted hover:bg-sunken hover:text-ink`,
  /** Icon-only inside a table row or menu: no border. */
  iconBare: `${CONTROL} size-8 shrink-0 rounded-full text-muted hover:bg-sunken hover:text-ink`,
} as const;

/** Form controls. Labels sit above, hints and errors below. */
export const field = {
  label: "block text-sm font-medium text-ink-2",
  hint: "mt-1 text-xs text-muted",
  error: "mt-1 text-sm text-danger",
  input:
    "mt-1.5 block h-10 w-full rounded-xl border border-field bg-surface px-3 text-sm text-ink placeholder:text-muted disabled:bg-sunken aria-[invalid=true]:border-danger",
  /** Numbers, tokens, ids: same box, mono text. */
  inputMono:
    "mt-1.5 block h-10 w-full rounded-xl border border-field bg-surface px-3 font-mono text-sm text-ink disabled:bg-sunken aria-[invalid=true]:border-danger",
  select:
    "mt-1.5 block h-10 w-full rounded-xl border border-field bg-surface px-3 text-sm text-ink disabled:bg-sunken",
  textarea:
    "mt-1.5 block w-full rounded-xl border border-field bg-surface px-3 py-2.5 text-sm text-ink placeholder:text-muted disabled:bg-sunken aria-[invalid=true]:border-danger",
  checkbox: "size-4 rounded accent-accent",
  /** A search box or filter in a toolbar: pill-shaped, icon inside. */
  search:
    "flex h-9 items-center gap-2 rounded-full border border-line bg-surface px-3.5 text-sm text-muted focus-within:border-accent",
} as const;

/** Containers. */
export const surface = {
  /** A white (or dark surface) card on the canvas. */
  card: "rounded-2xl border border-line bg-surface",
  /** Padded card. */
  panel: "rounded-2xl border border-line bg-surface p-5",
  /** Upload drop zone. */
  dropzone: "rounded-2xl border-[1.5px] border-dashed border-field p-6 text-center text-sm text-muted",
  /** Popover menus and dialogs. */
  popover: "rounded-2xl border border-line bg-surface p-1.5 shadow-[0_12px_32px_var(--ds-scrim)]",
} as const;

/** Data tables: wrap the <table> in `table.wrap` so wide tables scroll inside the card. */
export const table = {
  wrap: "overflow-x-auto rounded-2xl border border-line bg-surface",
  table: "w-full border-collapse text-sm",
  th: "px-3 py-3 text-left text-xs font-medium text-muted first:pl-5 last:pr-5",
  thNumeric: "px-3 py-3 text-right text-xs font-medium text-muted first:pl-5 last:pr-5",
  row: "border-t border-line-soft",
  td: "px-3 py-3.5 align-middle text-ink first:pl-5 last:pr-5",
  tdNumeric: "px-3 py-3.5 text-right align-middle font-mono text-[13px] text-ink first:pl-5 last:pr-5",
  tdMuted: "px-3 py-3.5 align-middle text-muted first:pl-5 last:pr-5",
  /** The name cell's link. */
  link: "font-medium text-ink hover:text-accent",
} as const;

/** Type. */
export const text = {
  /** Page title (one per page). */
  title: "text-[32px] leading-tight font-medium tracking-[-0.02em] text-ink",
  /** Section heading inside a page. */
  heading: "text-lg font-medium text-ink",
  /** Card or panel heading. */
  subheading: "text-base font-semibold text-ink",
  body: "text-[15px] text-ink",
  muted: "text-sm text-muted",
  small: "text-xs text-muted",
  mono: "font-mono text-[13px]",
  link: "font-medium text-accent underline-offset-4 hover:underline",
} as const;

/** Inline messages. Use `role="alert"` for errors, `role="status"` for the rest. */
export const notice = {
  info: "rounded-xl bg-sunken px-3.5 py-2.5 text-sm text-ink-2",
  success: "rounded-xl bg-accent-soft px-3.5 py-2.5 text-sm text-accent-ink",
  warning: "rounded-xl bg-flag-soft px-3.5 py-2.5 text-sm text-flag",
  error: "rounded-xl bg-danger-soft px-3.5 py-2.5 text-sm text-danger",
} as const;

/** Page layout. */
export const layout = {
  /** The width every signed-in page's content sits in, under the top bar. */
  page: "mx-auto w-full max-w-[1160px] px-4 py-8 sm:px-8 sm:py-10",
  /** Vertical rhythm between a page's blocks. */
  stack: "flex flex-col gap-7",
  /** A toolbar row: search, filters, then the primary action. */
  toolbar: "flex flex-wrap items-center gap-3",
  /** Stat cards under a page header. */
  stats: "grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-4",
} as const;
