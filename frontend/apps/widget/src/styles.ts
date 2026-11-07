// Plain styles for the tracer widget; the Organisation's Theme replaces them in ticket 06-03.
export const STYLES = `
*, *::before, *::after { box-sizing: border-box; }
html, body { margin: 0; height: 100%; font: 15px/1.4 system-ui, sans-serif; color: #0f172a; background: #fff; }
#root { height: 100%; }
.widget { display: flex; flex-direction: column; height: 100%; padding: 12px; gap: 8px; }
.widget h1 { margin: 0; font-size: 1.1rem; }
.messages { flex: 1; overflow-y: auto; list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.messages li { padding: 8px 10px; border-radius: 8px; white-space: pre-wrap; }
.messages li p { margin: 0; }
.visitor { background: #e2e8f0; align-self: flex-end; max-width: 85%; }
.agent { border: 1px solid #cbd5e1; max-width: 95%; }
.sources { margin-top: 4px !important; font-size: 0.8rem; color: #334155; }
[role="alert"] { margin: 0; padding: 6px 8px; border-radius: 6px; background: #fef2f2; color: #991b1b; }
form { display: grid; gap: 4px; }
label { font-weight: 600; font-size: 0.9rem; }
textarea { width: 100%; font: inherit; padding: 6px 8px; border: 1px solid #64748b; border-radius: 6px; }
button { justify-self: end; font: inherit; padding: 6px 14px; border: 1px solid #0f172a; border-radius: 6px; background: #0f172a; color: #fff; }
button:disabled { opacity: 0.6; }
`;
