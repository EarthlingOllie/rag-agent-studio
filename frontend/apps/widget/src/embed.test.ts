import { LAYOUT_MESSAGE, mount } from "./embed";

const STUDIO = "https://studio.example.test";

function script(attributes: Record<string, string>, src = `${STUDIO}/embed.js`) {
  const element = document.createElement("script");
  element.src = src;
  for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, value);
  document.body.append(element);
  return element;
}

/** A message as the widget in `frame` would post it to the host page. */
function post(frame: HTMLIFrameElement, data: unknown, origin = STUDIO, source: unknown = frame.contentWindow) {
  window.dispatchEvent(new MessageEvent("message", { data, origin, source: source as Window }));
}

function phone(matches: boolean) {
  // jsdom has no matchMedia; the loader asks it whether the host page is phone-sized.
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: matches && query === "(max-width: 640px)" }));
}

beforeEach(() => {
  document.body.innerHTML = "<p>Host page</p>";
  phone(false);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

test("injects an iframe for the Agent's widget shell, served from where the script came from", () => {
  const loader = script({ "data-agent": "agt_abc-DEF_123" });

  const frame = mount(loader);

  const iframes = document.querySelectorAll("iframe");
  expect(iframes).toHaveLength(1);
  expect(frame).toBe(iframes[0]);
  // The widget learns the host page's origin, the only one it will post its layout to.
  expect(frame?.src).toBe(`${STUDIO}/widget/a/agt_abc-DEF_123?host=${encodeURIComponent(window.location.origin)}`);
  expect(frame?.title).toBe("Chat");
  // Right after the snippet, so the widget appears where it was pasted.
  expect(loader.nextElementSibling).toBe(frame);
});

test("the Agent's public ID is escaped into the path", () => {
  const frame = mount(script({ "data-agent": "../../api/x?y#z" }));

  expect(new URL(frame?.src ?? "").pathname).toBe("/widget/a/..%2F..%2Fapi%2Fx%3Fy%23z");
});

test("does nothing without a data-agent attribute or a script", () => {
  const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);

  expect(mount(script({}))).toBeUndefined();
  expect(mount(null)).toBeUndefined();

  expect(document.querySelector("iframe")).toBeNull();
  expect(warn).toHaveBeenCalledWith("RAG Agent Studio embed: add data-agent with the Agent's public ID.");
});

test("by default the widget is a bubble: a small fixed frame in the corner until it opens", () => {
  const frame = mount(script({ "data-agent": "agt_hr" })) as HTMLIFrameElement;

  expect(new URL(frame.src).searchParams.has("launcher")).toBe(false);
  expect(frame.style.position).toBe("fixed");
  expect(frame.style.right).toBe("0px");
  expect(frame.style.bottom).toBe("0px");
  expect(frame.style.width).toBe("88px");
  expect(frame.style.height).toBe("88px");

  post(frame, { type: LAYOUT_MESSAGE, launcher: "bubble", open: true, position: "bottom-left" });

  expect(frame.style.left).toBe("0px");
  expect(frame.style.right).toBe("");
  expect(frame.style.width).toBe("min(420px, 100vw)");
  expect(frame.style.height).toBe("min(680px, 100vh)");

  post(frame, { type: LAYOUT_MESSAGE, launcher: "bubble", open: false, position: "bottom-left" });

  expect(frame.style.width).toBe("88px");
  expect(frame.style.height).toBe("88px");
});

test("an open bubble fills the screen on a phone", () => {
  phone(true);
  const frame = mount(script({ "data-agent": "agt_hr", "data-launcher": "bubble" })) as HTMLIFrameElement;
  expect(new URL(frame.src).searchParams.get("launcher")).toBe("bubble");

  post(frame, { type: LAYOUT_MESSAGE, launcher: "bubble", open: true, position: "bottom-right" });

  expect(frame.style.position).toBe("fixed");
  expect(frame.style.top).toBe("0px");
  expect(frame.style.left).toBe("0px");
  expect(frame.style.width).toBe("100%");
  expect(frame.style.height).toBe("100%");
});

test("data-launcher inline with data-target puts the widget inside the host's container", () => {
  document.body.innerHTML = '<p>Host page</p><div id="help"></div>';
  const loader = script({ "data-agent": "agt_hr", "data-launcher": "inline", "data-target": "#help" });

  const frame = mount(loader) as HTMLIFrameElement;

  expect(document.getElementById("help")?.firstElementChild).toBe(frame);
  expect(new URL(frame.src).searchParams.get("launcher")).toBe("inline");
  expect(frame.style.position).toBe("");
  expect(frame.style.width).toBe("100%");
  expect(frame.style.height).toBe("560px");
});

test("without a matching target the inline widget goes after the snippet", () => {
  const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
  const missing = script({ "data-agent": "agt_hr", "data-launcher": "inline", "data-target": "#nowhere" });
  const broken = script({ "data-agent": "agt_hr", "data-launcher": "inline", "data-target": "[[" });

  const afterMissing = mount(missing);
  const afterBroken = mount(broken);

  expect(missing.nextElementSibling).toBe(afterMissing);
  expect(broken.nextElementSibling).toBe(afterBroken);
  expect(warn).toHaveBeenCalledWith("RAG Agent Studio embed: data-target matches nothing; the widget follows the snippet.");
});

test("an unknown data-launcher is not passed on, so the Theme's Launcher applies", () => {
  const frame = mount(script({ "data-agent": "agt_hr", "data-launcher": "popup" })) as HTMLIFrameElement;

  expect(new URL(frame.src).searchParams.has("launcher")).toBe(false);

  // The widget then says which Launcher the Theme has.
  post(frame, { type: LAYOUT_MESSAGE, launcher: "inline", open: true, position: "bottom-right" });

  expect(frame.style.position).toBe("");
  expect(frame.style.height).toBe("560px");
});

test("layout messages are taken only from the widget's own frame and origin", () => {
  const frame = mount(script({ "data-agent": "agt_hr" })) as HTMLIFrameElement;
  const open = { type: LAYOUT_MESSAGE, launcher: "bubble", open: true, position: "bottom-right" };

  post(frame, open, "https://evil.example.test");
  post(frame, open, STUDIO, window);
  post(frame, { ...open, type: "something-else" });
  post(frame, null);

  expect(frame.style.width).toBe("88px");
  post(frame, open);
  expect(frame.style.width).toBe("min(420px, 100vw)");
});

test("the loader mounts the snippet's own script when it runs", async () => {
  const loader = script({ "data-agent": "agt_entry" });
  Object.defineProperty(document, "currentScript", { value: loader, configurable: true });

  await import("./loader");

  expect(new URL(document.querySelector("iframe")?.src ?? "").pathname).toBe("/widget/a/agt_entry");
  Reflect.deleteProperty(document, "currentScript");
});
