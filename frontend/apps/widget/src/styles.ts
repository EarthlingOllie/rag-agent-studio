// The widget's layout. Colours, radius and font come from the Theme: the shell inlines them as
// CSS custom properties on #root (`--theme-*`), which the shared UI primitives read. The page
// itself stays transparent, so a closed bubble shows only its Launcher on the host page.
export const STYLES = `
*, *::before, *::after { box-sizing: border-box; }
html, body { margin: 0; height: 100%; background: transparent; }
#root { height: 100%; font-family: var(--theme-font-family); color: var(--theme-on-surface); }
.widget { position: relative; height: 100%; }
.panel { position: absolute; inset: 0; display: flex; }
.widget[data-launcher="bubble"] .panel { inset: 12px 12px 80px 12px; }
.chat { flex: 1; min-width: 0; height: 100%; }
.chat li p { margin: 0; white-space: pre-wrap; }
.close { margin-left: 4px; width: 32px; height: 32px; border: 0; border-radius: 50%; background: transparent; color: inherit; font-size: 22px; line-height: 1; cursor: pointer; }
.sources { margin-top: 6px; font-size: 12px; color: var(--theme-muted); }
.sources details { margin-top: 2px; }
.sources summary { cursor: pointer; color: var(--theme-accent); }
.sources blockquote { margin: 4px 0 0; padding-left: 8px; border-left: 2px solid var(--theme-muted); white-space: pre-wrap; }
.error { margin: 0 10px; padding: 6px 8px; border-radius: 6px; background: #fef2f2; color: #991b1b; font-size: 14px; }
.starters { list-style: none; margin: 0; padding: 0 10px; display: flex; flex-wrap: wrap; gap: 6px; }
.starters button { font: inherit; font-size: 13px; padding: 6px 10px; border-radius: var(--theme-radius); border: 1px solid var(--theme-primary); background: var(--theme-surface); color: var(--theme-on-surface); cursor: pointer; }
@media (max-width: 640px) {
  .widget[data-launcher="bubble"][data-open="true"] .panel { inset: 0; }
  .widget[data-launcher="bubble"][data-open="true"] .chat { border-radius: 0 !important; }
  .widget[data-launcher="bubble"][data-open="true"] .launcher { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; scroll-behavior: auto !important; }
}
`;
