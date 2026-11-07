/**
 * The Embed Snippet's loader: one classic script, no framework and no globals. It reads the
 * snippet's `data-agent` (the Agent's public ID), optional `data-launcher` (`bubble` or
 * `inline`; without it the Theme's Launcher applies) and `data-target` (a selector for the
 * inline container), and injects an iframe for the widget shell, served from the origin the
 * script itself came from.
 *
 * The widget sizes its frame by posting layout messages to the host page. They are sent only
 * to the host's origin (passed in the frame's address), and taken here only from the frame's
 * own window and origin.
 */
export const LAYOUT_MESSAGE = "rag-agent-studio:layout";

export type Layout = { launcher: "bubble" | "inline"; open: boolean; position: "bottom-right" | "bottom-left" };

function warn(text: string) {
  console.warn(`RAG Agent Studio embed: ${text}`);
}

/** Sizes the frame: in place for inline; else a fixed corner, the whole screen when open on a phone. */
function layout(frame: HTMLIFrameElement, { launcher, open, position }: Layout) {
  let css = "border:0;color-scheme:normal;";
  if (launcher === "inline") css += "display:block;width:100%;height:560px";
  else if (open && matchMedia("(max-width: 640px)").matches) css += "position:fixed;z-index:2147483000;top:0;left:0;width:100%;height:100%";
  else
    css += `position:fixed;z-index:2147483000;bottom:0;${position === "bottom-left" ? "left" : "right"}:0;${
      open ? "width:min(420px, 100vw);height:min(680px, 100vh)" : "width:88px;height:88px"
    }`;
  frame.style.cssText = css;
}

function target(selector: string | null): Element | null {
  try {
    return selector ? document.querySelector(selector) : null;
  } catch {
    return null;
  }
}

export function mount(script: HTMLOrSVGScriptElement | null): HTMLIFrameElement | undefined {
  const agent = script?.getAttribute("data-agent");
  if (!script || !agent) {
    warn("add data-agent with the Agent's public ID.");
    return undefined;
  }
  const launcher = script.getAttribute("data-launcher");
  const selector = script.getAttribute("data-target");
  const src = new URL(`/widget/a/${encodeURIComponent(agent)}`, (script as HTMLScriptElement).src);
  src.searchParams.set("host", location.origin);
  if (launcher === "bubble" || launcher === "inline") src.searchParams.set("launcher", launcher);
  const frame = document.createElement("iframe");
  frame.src = src.href;
  frame.title = "Chat";
  layout(frame, { launcher: launcher === "inline" ? "inline" : "bubble", open: false, position: "bottom-right" });
  const container = target(selector);
  if (selector && !container) warn("data-target matches nothing; the widget follows the snippet.");
  if (container) container.append(frame);
  else script.after(frame);
  addEventListener("message", (event: MessageEvent<(Layout & { type?: string }) | null>) => {
    if (event.source === frame.contentWindow && event.origin === src.origin && event.data?.type === LAYOUT_MESSAGE) {
      layout(frame, event.data);
    }
  });
  return frame;
}
