// The widget's layout. Colours, radius and font come from the Theme: the shell inlines them as
// CSS custom properties on #root (`--theme-*`), which the shared UI primitives read. The page
// itself stays transparent, so a closed bubble shows only its Launcher on the host page.
//
// WCAG 2.2 AA: every control shows a 2 px focus ring in the text colour of what it sits on
// (so it contrasts as the Theme's text does), every control is at least 24 × 24 px, and the
// bubble's opening animation, like any other, is off for Visitors who prefer reduced motion.
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
.chat li.refusal { border: 1px solid #b45309; }
.sources { margin-top: 6px; font-size: 12px; color: var(--theme-muted); }
.sources details { margin-top: 2px; }
.sources summary { cursor: pointer; color: var(--theme-accent); }
.sources blockquote { margin: 4px 0 0; padding-left: 8px; border-left: 2px solid var(--theme-muted); white-space: pre-wrap; }
.feedback { margin-top: 6px; font-size: 12px; }
.thumbs { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; }
.thumbs button, .comment-actions button { font: inherit; font-size: 12px; min-width: 32px; min-height: 28px; padding: 2px 8px; border-radius: var(--theme-radius); border: 1px solid var(--theme-muted); background: transparent; color: inherit; cursor: pointer; }
.thumbs button[aria-pressed="true"] { border-color: var(--theme-primary); background: var(--theme-primary); color: var(--theme-on-primary); }
.thumbs button:disabled, .comment-actions button:disabled { opacity: 0.6; cursor: default; }
.thumbs button:focus-visible, .comment-actions button:focus-visible, .comment-form textarea:focus-visible { outline: 2px solid var(--theme-accent); outline-offset: 2px; }
.comment { margin: 4px 0 0; font-style: italic; white-space: pre-wrap; }
.comment-form { display: grid; gap: 4px; margin-top: 4px; }
.comment-form label { display: grid; gap: 2px; }
.comment-form textarea { font: inherit; font-size: 13px; width: 100%; resize: vertical; padding: 4px 6px; border-radius: var(--theme-radius); border: 1px solid var(--theme-muted); background: var(--theme-surface); color: var(--theme-on-surface); }
.comment-actions { display: flex; gap: 4px; }
.feedback-notice { margin: 4px 0 0; color: var(--theme-muted); }
.feedback-error { margin: 4px 0 0; padding: 4px 6px; border-radius: 6px; background: #fef2f2; color: #991b1b; }
.rating { margin: 0 10px; padding: 8px 10px; border: 1px solid var(--theme-muted); border-radius: var(--theme-radius); font-size: 13px; }
.rating p { margin: 0; }
.rating.rated { border-style: dashed; }
.scores { display: flex; flex-wrap: wrap; gap: 4px; margin: 6px 0; }
.scores button, .rating-actions button, .rating.rated button { font: inherit; font-size: 13px; min-width: 40px; min-height: 28px; padding: 2px 8px; border-radius: var(--theme-radius); border: 1px solid var(--theme-muted); background: transparent; color: inherit; cursor: pointer; }
.scores button[aria-pressed="true"] { border-color: var(--theme-primary); background: var(--theme-primary); color: var(--theme-on-primary); }
.scores button:disabled, .rating-actions button:disabled { opacity: 0.6; cursor: default; }
.rating-actions { display: flex; flex-wrap: wrap; gap: 4px; }
.rating-notice { margin-top: 4px !important; color: var(--theme-muted); }
.rating-error { margin-top: 4px !important; padding: 4px 6px; border-radius: 6px; background: #fef2f2; color: #991b1b; }
.controls { display: inline-flex; gap: 4px; }
.controls button { font: inherit; font-size: 12px; font-weight: 400; min-height: 28px; padding: 3px 8px; border-radius: var(--theme-radius); border: 1px solid currentColor; background: transparent; color: inherit; cursor: pointer; }
.controls button:disabled { opacity: 0.6; cursor: default; }
.notice { margin: 0; padding: 10px; }
.ended { display: grid; gap: 8px; justify-items: start; }
.ended p { margin: 0; }
.ended button { font: inherit; font-size: 14px; padding: 6px 12px; border-radius: var(--theme-radius); border: 0; background: var(--theme-primary); color: var(--theme-on-primary); cursor: pointer; }
.error { margin: 0 10px; padding: 6px 8px; border-radius: 6px; background: #fef2f2; color: #991b1b; font-size: 14px; }
.starters { list-style: none; margin: 0; padding: 0 10px; display: flex; flex-wrap: wrap; gap: 6px; }
.starters button { font: inherit; font-size: 13px; padding: 6px 10px; border-radius: var(--theme-radius); border: 1px solid var(--theme-primary); background: var(--theme-surface); color: var(--theme-on-surface); cursor: pointer; }
:focus-visible { outline: 2px solid var(--theme-on-surface) !important; outline-offset: 2px; }
.chat header :focus-visible, .launcher :focus-visible { outline-color: var(--theme-on-primary) !important; }
.launcher :focus-visible { outline-offset: -6px; }
.sources summary { min-height: 24px; }
@keyframes widget-open { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
.widget[data-launcher="bubble"] .panel { animation: widget-open 160ms ease-out; }
@media (max-width: 640px) {
  .widget[data-launcher="bubble"][data-open="true"] .panel { inset: 0; }
  .widget[data-launcher="bubble"][data-open="true"] .chat { border-radius: 0 !important; }
  .widget[data-launcher="bubble"][data-open="true"] .launcher { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; scroll-behavior: auto !important; }
}
`;
