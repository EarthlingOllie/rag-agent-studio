/**
 * The Embed Snippet's loader: one classic script, no framework and no globals. It reads the
 * snippet's `data-agent` (the Agent's public ID) and injects an iframe for the widget shell,
 * served from the origin the script itself came from, right after the snippet.
 */
export function mount(script: HTMLOrSVGScriptElement | null): HTMLIFrameElement | undefined {
  const agent = script?.getAttribute("data-agent");
  if (!script || !agent) {
    console.warn("RAG Agent Studio embed: add data-agent with the Agent's public ID.");
    return undefined;
  }
  const frame = document.createElement("iframe");
  frame.src = new URL(`/widget/a/${encodeURIComponent(agent)}`, (script as HTMLScriptElement).src).href;
  frame.title = "Chat";
  frame.style.cssText = "border:0;width:100%;max-width:420px;height:560px;color-scheme:normal";
  script.after(frame);
  return frame;
}
