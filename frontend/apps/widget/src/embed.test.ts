import { mount } from "./embed";

function script(attributes: Record<string, string>, src = "https://studio.example.test/embed.js") {
  const element = document.createElement("script");
  element.src = src;
  for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, value);
  document.body.append(element);
  return element;
}

beforeEach(() => {
  document.body.innerHTML = "<p>Host page</p>";
});

test("injects an iframe for the Agent's widget shell, served from where the script came from", () => {
  const loader = script({ "data-agent": "agt_abc-DEF_123" });

  const frame = mount(loader);

  const iframes = document.querySelectorAll("iframe");
  expect(iframes).toHaveLength(1);
  expect(frame).toBe(iframes[0]);
  expect(frame?.src).toBe("https://studio.example.test/widget/a/agt_abc-DEF_123");
  expect(frame?.title).toBe("Chat");
  // Right after the snippet, so the widget appears where it was pasted.
  expect(loader.nextElementSibling).toBe(frame);
});

test("the Agent's public ID is escaped into the path", () => {
  const frame = mount(script({ "data-agent": "../../api/x?y#z" }));

  expect(frame?.src).toBe("https://studio.example.test/widget/a/..%2F..%2Fapi%2Fx%3Fy%23z");
});

test("does nothing without a data-agent attribute or a script", () => {
  const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);

  expect(mount(script({}))).toBeUndefined();
  expect(mount(null)).toBeUndefined();

  expect(document.querySelector("iframe")).toBeNull();
  expect(warn).toHaveBeenCalledWith("RAG Agent Studio embed: add data-agent with the Agent's public ID.");
});

test("the loader mounts the snippet's own script when it runs", async () => {
  const loader = script({ "data-agent": "agt_entry" });
  Object.defineProperty(document, "currentScript", { value: loader, configurable: true });

  await import("./loader");

  expect(document.querySelector("iframe")?.src).toBe("https://studio.example.test/widget/a/agt_entry");
  Reflect.deleteProperty(document, "currentScript");
});
